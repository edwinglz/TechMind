"""Generate a diagnostic brief for a ticket.

Two engines produce the same validated shape (app/ai/schema.py):
- mock: builds the brief straight from the company's own data. Causes are the
  known issues that best match the report, ranked by symptom overlap and recent
  frequency, then re-ranked by the answers collected and any failed self-fix.
  It costs nothing and makes the whole product usable without an API key.
- live: sends the same retrieved context to Claude (app/ai/client.py), which
  can read the photo and reason beyond keyword overlap.

If a live call fails, the previous brief (or a mock one) is shown with a
notice, so a demo never stalls on a network problem.

Costs are always computed here, in code, from the parts price list and the
company's rates; the AI only picks part ids and minutes.
"""

import logging

from sqlmodel import Session, select

from app.ai.schema import BriefData, Cause, Question, SelfFix, Source
from app.config import settings
from app.models import Brief, Company, Ticket, TicketEvent
from app.services.insights import recommended_parts
from app.services.retrieval import Context, build_context, stems
from app.templating import labels_for
from app.templating import midcase as _lower

log = logging.getLogger("techmind.brief")

MAX_CAUSES = 4


# ---------- shared helpers ----------

def latest_brief(session: Session, ticket_id: int) -> Brief | None:
    return session.exec(select(Brief).where(Brief.ticket_id == ticket_id).order_by(Brief.version.desc())).first()


def failed_self_fix(session: Session, ticket: Ticket) -> dict | None:
    """The most recent self-fix that the reporter tried without success, if any."""
    event = session.exec(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id,
                                                   TicketEvent.type == "self_fix_outcome")
                         .order_by(TicketEvent.created_at.desc())).first()
    if event and not event.payload.get("resolved"):
        return event.payload
    return None


def asked_before(session: Session, ticket_id: int) -> list[str]:
    """Every question shown in any earlier version of this ticket's brief, oldest first."""
    seen: dict[str, None] = {}
    for brief in session.exec(select(Brief).where(Brief.ticket_id == ticket_id).order_by(Brief.version)):
        for q in brief.data.get("questions_for_reporter", []):
            seen.setdefault(q["question"], None)
    return list(seen)


def _too_similar(a: str, b: str) -> bool:
    """True when two questions ask about essentially the same thing.

    Compares word stems: if most of the shorter question's words appear in the other one, a
    reporter would hear it as the same question again."""
    filler = {"if", "how", "which", "you", "they", "see", "look", "check", "there", "does", "example", "compar"}
    sa, sb = stems(a) - filler, stems(b) - filler
    if not sa or not sb:
        return False
    shared = len(sa & sb)
    return shared >= 3 and shared / min(len(sa), len(sb)) >= 0.5


def drop_repeat_questions(questions: list[dict], previous: list[str], answers: dict) -> list[dict]:
    """Remove questions that repeat or rephrase an earlier one.

    A question already answered is never asked again in any wording. An earlier question that
    wasn't answered may stay, but only word for word (so a rephrased copy doesn't pile up)."""
    kept: list[dict] = []
    for q in questions:
        text = q["question"]
        if text in answers:
            continue
        if any(_too_similar(text, old) for old in previous if old != text):
            continue
        if any(_too_similar(text, k["question"]) for k in kept):
            continue
        kept.append(q)
    return kept


def _answers_text(answers: dict) -> str:
    return " ".join(f"{q} {a.get('note', '')}" for q, a in answers.items() if a.get("answer") == "yes")


# ---------- mock engine ----------

def _phrases(symptoms: str) -> list[str]:
    return [p.strip() for p in symptoms.split(";") if p.strip()]


def _mock(ctx: Context, labels: dict, answers: dict, self_fix: dict | None, previous: dict | None) -> BriefData:
    profile = ctx.company.profile
    report = stems(ctx.ticket.description)
    candidates = ctx.issues[: MAX_CAUSES + 3]
    scores = {m.stat.issue.ref: m.score for m in candidates}
    notes: dict[str, list[str]] = {ref: [] for ref in scores}

    # Answers re-rank the causes their question was about: yes raises, no lowers.
    asked = {q["question"]: q for q in (previous or {}).get("questions_for_reporter", [])}
    title_to_ref = {m.stat.issue.title: m.stat.issue.ref for m in candidates}
    for question, answer in answers.items():
        for title in asked.get(question, {}).get("rules_in_or_out", []):
            ref = title_to_ref.get(title)
            if ref and answer.get("answer") in ("yes", "no"):
                scores[ref] += 4 if answer["answer"] == "yes" else -4
                notes[ref].append(f"{labels['reporter'].capitalize()} answered {answer['answer']} to “{question}”.")

    # A self-fix that didn't help rules out the causes it targeted.
    if self_fix:
        for ref in self_fix.get("targets", []):
            if ref in scores:
                scores[ref] -= 6
                notes[ref].append(f"The {labels['reporter']} already tried the self-fix for this and it didn't help.")

    ranked = sorted(candidates, key=lambda m: -scores[m.stat.issue.ref])[:MAX_CAUSES]
    top_score = max(scores[ranked[0].stat.issue.ref], 1) if ranked else 1
    history_refs = {issue.ref: past for past, issue in ctx.asset_history if issue}

    causes = []
    for rank, m in enumerate(ranked):
        s, issue = m.stat, m.stat.issue
        score = scores[issue.ref]
        likelihood = "high" if rank == 0 and score > 0 else "medium" if score >= 0.45 * top_score else "low"
        matched = sorted({w for w in report & stems(f"{issue.title} {issue.symptoms}")})
        evidence = []
        if matched:
            evidence.append(f"The report's wording ({', '.join(matched)}) matches this issue's listed symptoms: {issue.symptoms}.")
        else:
            evidence.append(f"Listed symptoms: {issue.symptoms}.")
        if s.last90:
            trend = {"rising": ", and rising", "fading": ", and fading"}.get(s.trend, "")
            evidence.append(f"Logged {s.last90} times across the company in the last 90 days{trend}.")
        if issue.ref in history_refs:
            past = history_refs[issue.ref]
            evidence.append(f"This unit had it on {past.created_at:%b %d} ({past.ref}).")
        evidence += notes[issue.ref]

        sources = [Source(type="known_issue", ref=issue.ref)]
        issue_stems = stems(issue.title)
        for chunk in ctx.manual:
            if chunk.product_id == issue.product_id and issue_stems & stems(chunk.section_title + " " + chunk.content[:400]):
                sources.append(Source(type="manual", ref=chunk.section_title))
                break
        sources += [Source(type="past_ticket", ref=p.ref) for p, i in ctx.similar if i and i.id == issue.id][:2]
        if issue.ref in history_refs:
            sources.append(Source(type="asset_history", ref=history_refs[issue.ref].ref))

        rec = s.recommended
        causes.append(Cause(
            issue_id=issue.ref, cause=issue.title, likelihood=likelihood, evidence=" ".join(evidence),
            sources=sources,
            confirm_steps=[f"Look for: {p[0].lower() + p[1:]}" for p in _phrases(issue.symptoms)[:3]],
            fix_steps=list(rec.variant.steps) if rec else [],
            part_ids=[p for p in recommended_parts(s) if p in ctx.parts],
            estimated_minutes=(rec.avg_minutes if rec and rec.avg_minutes else issue.avg_minutes) or 30,
        ))

    # Self-fix: the steps for the likely causes the reporter is allowed to handle.
    fixable = [m for m in ranked if m.stat.issue.reporter_fixable and scores[m.stat.issue.ref] > 0][:2]
    if self_fix and not answers:
        fixable = [m for m in fixable if m.stat.issue.ref not in self_fix.get("targets", [])]
    reporter_fix = SelfFix()
    if fixable:
        steps = []
        for m in fixable:
            listed = next((v for v in m.stat.variants if v.variant.source == "import"), m.stat.recommended)
            steps += [step for step in listed.variant.steps if step not in steps]
        forbidden = profile.get("self_fix_forbidden", [])[:2]
        reporter_fix = SelfFix(applicable=True, steps=steps, targets=[m.stat.issue.ref for m in fixable],
                               risk_note=("Stop after these steps. " + labels["reporters"].capitalize() + " must not try: "
                                          + "; ".join(forbidden) + ".") if forbidden else "Stop after these steps.")

    # Questions: for each cause, ask about the symptom that best tells it apart from the others.
    questions = []
    if not ctx.asset:
        questions.append(Question(question=f"Which {labels['asset']} is it? Read the model from the nameplate.",
                                  why="The model decides which manual and known issues apply.", rules_in_or_out=[]))
    other_words = {m.stat.issue.ref: set().union(*(stems(o.stat.issue.symptoms) for o in ranked if o is not m) or [set()])
                   for m in ranked}
    for m in ranked:
        issue = m.stat.issue
        options = [p for p in _phrases(issue.symptoms) if not stems(p) <= report]
        if not options:
            continue
        # Prefer a symptom the report didn't already mention and the other causes don't share.
        best = max(options, key=lambda p: len(stems(p) - other_words[issue.ref] - report) - 2 * len(stems(p) & report))
        text = best[0].upper() + best[1:] + "?"
        if text in answers:
            continue
        questions.append(Question(question=text, rules_in_or_out=[issue.title],
                                  why=f"Yes points to {_lower(issue.title)}; no makes it less likely."))
    questions = questions[:5]

    # Safety topics that share at least two words with the likely causes, their fix steps and the
    # equipment category. (Titles and fix steps only: symptom text like "motor hot to the touch"
    # would otherwise match "hot oil".)
    cause_text = " ".join(f"{c.cause} {' '.join(c.fix_steps)}" for c in causes[:3])
    cause_stems = stems(cause_text + " " + " ".join(p.category for p in ctx.products))
    scored = []
    for topic in profile.get("safety_topics", []):
        head = topic.split(":")[0]  # the hazard's name, e.g. "gas leaks"
        if stems(head) & cause_stems:
            scored.append((len(stems(topic) & cause_stems), topic))
    warnings = [topic for score, topic in sorted(scored, key=lambda x: -x[0]) if score >= 2]
    warnings = warnings[:3]

    where = f"{ctx.product.model_name} at {ctx.site.name}" if ctx.product else f"unknown {labels['asset']} at {ctx.site.name}"
    top = _lower(causes[0].cause) if causes else "unclear"
    summary = f"{where}: most likely {top}."
    if len(causes) > 1:
        summary += f" Also check {_lower(causes[1].cause)}."
    if ctx.repeat_failure:
        summary += f" Repeat failure: {ctx.repeat_count} tickets on this unit in 60 days."
    interpretation = (f"“{ctx.ticket.description}” fits the known symptoms of "
                      + " and ".join(_lower(c.cause) for c in causes[:2]) + "." if causes else
                      f"“{ctx.ticket.description}” doesn't match any known issue yet.")

    missing = []
    if not ctx.ticket.photo_path:
        missing.append("No photo yet. A photo of the unit and any error display would help.")
    if not ctx.asset:
        missing.append(f"The exact {labels['asset']} and model.")
    images = (["Photo attached. Image analysis runs in live mode."] if ctx.ticket.photo_path else [])

    return BriefData(summary=summary, symptom_interpretation=interpretation, image_findings=images,
                     probable_causes=causes, reporter_self_fix=reporter_fix, questions_for_reporter=questions,
                     safety_warnings=warnings, missing_info=missing)


# ---------- costs and part names (always computed, never trusted to the AI) ----------

def _enrich(data: dict, ctx: Context) -> dict:
    company, onsite = ctx.company, ctx.ticket.service_mode == "onsite" or ctx.ticket.assigned_user_id is not None
    for cause in data["probable_causes"]:
        parts = [ctx.parts[p] for p in cause["part_ids"] if p in ctx.parts]
        cause["part_ids"] = [p.ref for p in parts]
        parts_total = sum(p.unit_price for p in parts)
        labor = company.labor_rate_per_hour * cause["estimated_minutes"] / 60
        trip = company.trip_fee if onsite else 0
        cause["cost"] = {
            "parts": [{"ref": p.ref, "name": p.name, "price": p.unit_price, "in_stock": p.in_stock} for p in parts],
            "parts_total": parts_total, "labor": labor, "trip": trip, "total": parts_total + labor + trip,
        }
    fix = data["reporter_self_fix"]
    if fix["applicable"]:
        targets = [c for c in data["probable_causes"] if c["issue_id"] in fix.get("targets", [])]
        minutes = max((c["estimated_minutes"] for c in targets), default=30)
        fix["savings"] = company.trip_fee + company.labor_rate_per_hour * minutes / 60
    return data


# ---------- entry point ----------

def generate(session: Session, ticket: Ticket, actor_id: int | None, refine: bool = False) -> Brief:
    company = session.get(Company, ticket.company_id)
    labels = labels_for(company)
    previous = latest_brief(session, ticket.id)
    answers = ticket.answers or {}
    previous_questions = asked_before(session, ticket.id)
    self_fix = failed_self_fix(session, ticket)
    ctx = build_context(session, ticket, extra_text=_answers_text(answers))

    mode, model, tokens_in, tokens_out, is_fallback = "mock", "", 0, 0, False
    data = None
    if settings.ai_mode == "live":
        from app.ai import client, prompts

        note = None
        if self_fix:
            note = " | ".join(self_fix.get("steps", [])) + " -> did not fix it"
        try:
            brief, tokens_in, tokens_out = client.diagnose(
                prompts.system_prompt(ctx, labels), prompts.user_prompt(ctx, labels, answers, note, previous_questions),
                ticket.photo_path)
            data, mode, model = brief.model_dump(), "live", client.BRIEF_MODEL
        except Exception as error:  # network, key, or invalid output: never leave the page empty
            log.warning("live brief failed, falling back: %s", error)
            is_fallback = True
            if previous and previous.ai_mode == "live":
                data = {k: v for k, v in previous.data.items()}
    if data is None:
        data = _mock(ctx, labels, answers, self_fix, previous.data if previous else None).model_dump()

    data["questions_for_reporter"] = drop_repeat_questions(data.get("questions_for_reporter", []),
                                                           previous_questions, answers)
    data = _enrich(data, ctx)
    data["context"] = {"repeat_count": ctx.repeat_count, "repeat_failure": ctx.repeat_failure,
                       "manual_sections": len(ctx.manual), "similar_tickets": len(ctx.similar),
                       "issues_considered": min(len(ctx.issues), 10)}
    brief = Brief(company_id=ticket.company_id, ticket_id=ticket.id, version=(previous.version + 1 if previous else 1),
                  data=data, ai_mode=mode, model=model, input_tokens=tokens_in, output_tokens=tokens_out,
                  is_fallback=is_fallback)
    session.add(brief)
    session.add(TicketEvent(company_id=ticket.company_id, ticket_id=ticket.id,
                            type="brief_refined" if refine else "brief_generated", actor_user_id=actor_id,
                            payload={"version": brief.version, "mode": mode, "fallback": is_fallback,
                                     "top_cause": data["probable_causes"][0]["cause"] if data["probable_causes"] else None}))
    return brief
