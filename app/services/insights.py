"""What the ticket history says about each known issue: how often it happens,
whether it is rising or fading, and which fix currently works best.

Everything here is computed from the tickets table on demand, so the numbers
always match the history and change the moment a ticket closes. That is the
whole "learning" story: no model training, just plain counting that anyone can
check.

Rules (also described in docs/ARCHITECTURE.md):
- Frequency (recency-weighted): each ticket in the last 90 days counts
  1 - age/90, so a ticket from yesterday counts almost 1 and one from two
  months ago about 0.33.
- Trend: "rising" if the last 30 days have more tickets than the 30 before and
  at least 2; "fading" is the mirror image.
- Fix variants: attempts are technician tickets that used the variant;
  successes are the resolved ones. The recommended fix is the variant with the
  highest success rate among variants with at least 3 attempts (ties go to the
  faster one). Until a variant has 3 attempts, the company's own listed fix
  is recommended.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, select

from app.config import today
from app.models import FixVariant, KnownIssue, Ticket

MIN_ATTEMPTS = 3
RECENT_DAYS = 90
TREND_WINDOW = 30
TREND_MIN = 2


@dataclass
class VariantStat:
    variant: FixVariant
    attempts: int = 0
    successes: int = 0
    total_minutes: int = 0
    last_used: datetime | None = None
    part_refs: list = field(default_factory=list)

    @property
    def success_rate(self) -> float | None:
        return self.successes / self.attempts if self.attempts else None

    @property
    def avg_minutes(self) -> int | None:
        return round(self.total_minutes / self.attempts) if self.attempts else None


@dataclass
class IssueStat:
    issue: KnownIssue
    weighted: float = 0.0  # recency-weighted frequency over the last 90 days
    last90: int = 0
    last30: int = 0
    prior30: int = 0
    total: int = 0
    by_reporter: int = 0
    last_seen: datetime | None = None
    variants: list[VariantStat] = field(default_factory=list)
    recommended: VariantStat | None = None
    recommended_changed: bool = False  # True when the best fix is no longer the company's listed one

    @property
    def trend(self) -> str | None:
        if self.last30 > self.prior30 and self.last30 >= TREND_MIN:
            return "rising"
        if self.prior30 > self.last30 and self.prior30 >= TREND_MIN:
            return "fading"
        return None


def _age_days(when: datetime) -> int:
    """Days since a ticket was opened. Never negative: tickets are stored in UTC (already
    "tomorrow" in the evening in the Americas), and with AS_OF_DATE pinned for the demo, tickets
    created during the demo would otherwise look like they're from the future and be skipped."""
    return max((today() - when.date()).days, 0)


def issue_stats(session: Session, company_id: int, product_ids: list[int] | None = None) -> dict[int, IssueStat]:
    """Stats for every known issue of the company (optionally only some products), keyed by issue id."""
    query = select(KnownIssue).where(KnownIssue.company_id == company_id)
    if product_ids is not None:
        query = query.where(KnownIssue.product_id.in_(product_ids))
    stats = {issue.id: IssueStat(issue=issue) for issue in session.exec(query)}
    if not stats:
        return stats

    variants = session.exec(select(FixVariant).where(FixVariant.known_issue_id.in_(stats.keys()))).all()
    vstats = {v.id: VariantStat(variant=v) for v in variants}

    tickets = session.exec(select(Ticket).where(
        Ticket.company_id == company_id, Ticket.known_issue_id.in_(stats.keys()),
        Ticket.closed_at.is_not(None))).all()

    for t in tickets:
        s = stats[t.known_issue_id]
        age = _age_days(t.created_at)
        s.total += 1
        s.by_reporter += t.resolved_by_reporter
        if s.last_seen is None or t.created_at > s.last_seen:
            s.last_seen = t.created_at
        if age < RECENT_DAYS:
            s.last90 += 1
            s.weighted += 1 - age / RECENT_DAYS
        if age < TREND_WINDOW:
            s.last30 += 1
        elif age < 2 * TREND_WINDOW:
            s.prior30 += 1
        if t.fix_variant_id in vstats and not t.resolved_by_reporter and t.resolved is not None:
            v = vstats[t.fix_variant_id]
            v.attempts += 1
            v.successes += bool(t.resolved)
            v.total_minutes += t.minutes or 0
            if v.last_used is None or t.created_at > v.last_used:
                v.last_used = t.created_at
                v.part_refs = list(t.part_refs or [])

    for v in vstats.values():
        stats[v.variant.known_issue_id].variants.append(v)

    for s in stats.values():
        listed = next((v for v in s.variants if v.variant.source == "import"), None)
        proven = [v for v in s.variants if v.attempts >= MIN_ATTEMPTS]
        best = max(proven, key=lambda v: (v.success_rate, -(v.avg_minutes or 0)), default=None)
        if best and listed and listed.attempts >= MIN_ATTEMPTS and listed.success_rate >= best.success_rate:
            best = listed  # the listed fix keeps the title on a tie
        s.recommended = best or listed or (s.variants[0] if s.variants else None)
        s.recommended_changed = bool(s.recommended and listed and s.recommended is not listed)
        s.variants.sort(key=lambda v: (v is not s.recommended, -(v.success_rate or 0), -v.attempts))
    return stats


def recommended_parts(stat: IssueStat) -> list[str]:
    """Parts for the recommended fix: the listed parts for the company's own fix,
    otherwise the parts technicians used the last time they applied it."""
    rec = stat.recommended
    if rec is None or rec.variant.source == "import":
        return list(stat.issue.part_refs or [])
    return list(rec.part_refs or [])


def dispatch_savings(session: Session, company) -> tuple[int, float]:
    """How many tickets the reporter fixed without a technician, and roughly what that saved
    (trip fee plus labor for the issue's usual repair time)."""
    rows = session.exec(select(Ticket, KnownIssue).join(KnownIssue, Ticket.known_issue_id == KnownIssue.id, isouter=True)
                        .where(Ticket.company_id == company.id, Ticket.resolved_by_reporter == True)).all()  # noqa: E712
    saved = 0.0
    for _ticket, issue in rows:
        minutes = issue.avg_minutes if issue else 30
        saved += company.trip_fee + company.labor_rate_per_hour * minutes / 60
    return len(rows), saved


def stats_by_product(stats: dict[int, IssueStat]) -> dict[int, list[IssueStat]]:
    grouped = defaultdict(list)
    for s in stats.values():
        grouped[s.issue.product_id].append(s)
    return grouped
