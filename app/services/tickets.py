"""Everything that changes a ticket, in one place, each step logged to ticket_events.

Lifecycle:
    new -> briefed -> (awaiting_self_fix -> closed, or back to briefed) -> assigned -> closed

Closing a ticket is where the knowledge base learns: the ticket is tied to a
known issue (or creates a new one) and to the fix variant that was used (or
creates a new variant). The stats in app/services/insights.py are computed from
these tickets, so trends and the recommended fix update immediately.
"""

import re
from datetime import datetime

from sqlmodel import Session, select

from app.config import settings
from app.models import FixVariant, KnownIssue, Ticket, TicketEvent, TicketStatus, utcnow
from app.services.fix_variants import normalize_steps
from app.services.retrieval import stems
from app.services.search import index_ticket


def log_event(session: Session, ticket: Ticket, type_: str, actor_id: int | None, **payload) -> TicketEvent:
    event = TicketEvent(company_id=ticket.company_id, ticket_id=ticket.id, type=type_, actor_user_id=actor_id,
                        payload=payload)
    session.add(event)
    return event


def next_ref(session: Session, company_id: int) -> str:
    refs = session.exec(select(Ticket.ref).where(Ticket.company_id == company_id)).all()
    numbers = [int(m.group(1)) for r in refs if (m := re.fullmatch(r"T-(\d+)", r))]
    return f"T-{max(numbers, default=0) + 1:04d}"


def create(session: Session, *, company_id: int, site_id: int, asset_id: int | None, product_id: int | None,
           description: str, service_mode: str, photo_path: str | None, actor_id: int) -> Ticket:
    ticket = Ticket(company_id=company_id, ref=next_ref(session, company_id), site_id=site_id, asset_id=asset_id,
                    product_id=product_id, description=description.strip(), service_mode=service_mode,
                    photo_path=photo_path, status=TicketStatus.NEW)
    session.add(ticket)
    session.flush()
    log_event(session, ticket, "created", actor_id, description=ticket.description, service_mode=service_mode)
    return ticket


def approve_self_fix(session: Session, ticket: Ticket, actor_id: int, steps: list[str], targets: list[str]) -> None:
    ticket.status = TicketStatus.AWAITING_SELF_FIX
    log_event(session, ticket, "self_fix_approved", actor_id, steps=steps, targets=targets)


def record_self_fix_outcome(session: Session, ticket: Ticket, actor_id: int, resolved: bool, note: str = "") -> None:
    approved = session.exec(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id,
                                                      TicketEvent.type == "self_fix_approved")
                            .order_by(TicketEvent.created_at.desc())).first()
    payload = dict(approved.payload) if approved else {}
    log_event(session, ticket, "self_fix_outcome", actor_id, resolved=resolved, note=note,
              steps=payload.get("steps", []), targets=payload.get("targets", []))
    if resolved:
        # Tie the ticket to the first targeted known issue, so it counts toward that issue's frequency.
        issue = None
        if payload.get("targets"):
            issue = session.exec(select(KnownIssue).where(KnownIssue.company_id == ticket.company_id,
                                                          KnownIssue.ref == payload["targets"][0])).first()
        ticket.known_issue_id = issue.id if issue else None
        ticket.resolved, ticket.resolved_by_reporter = True, True
        ticket.fix_description = "|".join(payload.get("steps", []))
        _close(session, ticket, actor_id)
    else:
        ticket.status = TicketStatus.BRIEFED


def assign(session: Session, ticket: Ticket, actor_id: int, technician) -> None:
    ticket.assigned_user_id = technician.id
    ticket.status = TicketStatus.ASSIGNED
    log_event(session, ticket, "assigned", actor_id, technician=technician.name)


def save_answer(session: Session, ticket: Ticket, actor_id: int, question: str, answer: str, note: str) -> None:
    answers = dict(ticket.answers or {})  # assign a new dict so SQLAlchemy notices the change
    if answer == "clear":
        answers.pop(question, None)
    else:
        answers[question] = {"answer": answer, "note": note.strip()}
        log_event(session, ticket, "question_answered", actor_id, question=question, answer=answer, note=note.strip())
    ticket.answers = answers


def _steps_from_text(value: str) -> list[str]:
    parts = [p.strip(" -•\t") for p in re.split(r"[\n|]|(?<=\.)\s+(?=[A-Z])", value)]
    return [p.rstrip(".") for p in parts if p]


def _match_variant(description: str, variants: list[FixVariant]) -> FixVariant | None:
    """Find the existing fix variant a free-text description refers to.

    Live mode asks Claude Haiku; mock mode (and any failure) uses word overlap.
    """
    if not variants:
        return None
    if settings.ai_mode == "live":
        try:
            from app.ai.client import match_fix

            index = match_fix(description, [v.steps for v in variants])
            return variants[index] if index is not None else None
        except Exception:
            pass
    described = stems(description)
    best, best_score = None, 0.0
    for v in variants:
        known = stems(" ".join(v.steps))
        score = len(described & known) / max(len(described | known), 1)
        if score > best_score:
            best, best_score = v, score
    return best if best_score >= 0.6 else None


def close(session: Session, ticket: Ticket, actor_id: int, *, issue_choice: str, new_issue_title: str,
          variant_choice: str, fix_description: str, part_refs: list[str], minutes: int, resolved: bool) -> None:
    """Record what was actually wrong and what fixed it, then update the knowledge base."""
    if issue_choice == "new":
        n = len(session.exec(select(KnownIssue.id).where(KnownIssue.company_id == ticket.company_id)).all()) + 1
        issue = KnownIssue(company_id=ticket.company_id, ref=f"KI-NEW-{n:02d}", product_id=ticket.product_id,
                           title=new_issue_title.strip() or "New issue", symptoms=ticket.description,
                           part_refs=part_refs, avg_minutes=minutes)
        session.add(issue)
        session.flush()
        ticket.new_issue_text = issue.title
        log_event(session, ticket, "known_issue_created", actor_id, ref=issue.ref, title=issue.title)
    else:
        issue = session.get(KnownIssue, int(issue_choice))

    variants = session.exec(select(FixVariant).where(FixVariant.known_issue_id == issue.id)).all()
    variant = None
    if variant_choice.isdigit():
        variant = session.get(FixVariant, int(variant_choice))
    elif fix_description.strip():
        steps = _steps_from_text(fix_description)
        variant = next((v for v in variants if normalize_steps(v.steps) == normalize_steps(steps)), None)
        variant = variant or _match_variant(fix_description, variants)
        if variant is None:
            variant = FixVariant(company_id=ticket.company_id, known_issue_id=issue.id, steps=steps, source="technician")
            session.add(variant)
            session.flush()
            log_event(session, ticket, "fix_variant_created", actor_id, steps=steps)

    from app.services.insights import issue_stats

    stat = issue_stats(session, ticket.company_id, [issue.product_id]).get(issue.id)
    recommended_id = stat.recommended.variant.id if stat and stat.recommended else None

    ticket.known_issue_id = issue.id
    ticket.fix_variant_id = variant.id if variant else None
    ticket.used_recommended_fix = bool(variant and variant.id == recommended_id)
    ticket.fix_description = "|".join(variant.steps) if variant else fix_description.strip()
    ticket.part_refs = part_refs
    ticket.minutes = minutes
    ticket.resolved = resolved
    _close(session, ticket, actor_id)


def _close(session: Session, ticket: Ticket, actor_id: int) -> None:
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = utcnow()
    if ticket.product_id:
        index_ticket(session, ticket)  # so future reports can find this one as a similar ticket
    issue = session.get(KnownIssue, ticket.known_issue_id) if ticket.known_issue_id else None
    log_event(session, ticket, "closed", actor_id, issue=issue.title if issue else None, resolved=ticket.resolved,
              by_reporter=ticket.resolved_by_reporter, minutes=ticket.minutes)


def age_text(when: datetime) -> str:
    seconds = (utcnow() - when).total_seconds()
    if seconds < 90:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h ago"
    return when.strftime("%b %d")
