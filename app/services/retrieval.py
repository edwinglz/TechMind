"""Gather everything the diagnosis needs for one ticket.

For a ticket we collect, all scoped to the company:
- the site, the asset (if known) and its model, or every model installed at
  the site when the asset is unknown
- the manual sections that best match the report (SQLite FTS5 keyword search)
- the model's known issues with their stats and current recommended fix,
  ranked by how well they match the report and how common they are lately
- similar resolved tickets for the same model(s)
- this unit's own recent tickets, and whether it counts as a repeat failure
- the parts that fit these models

The result is a plain `Context` object used by both the mock and the live brief.
"""

import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import text
from sqlmodel import Session, select

from app.config import today
from app.models import Asset, Company, KnownIssue, ManualChunk, Part, Product, Site, Ticket
from app.services.insights import IssueStat, issue_stats

REPEAT_WINDOW_DAYS = 60
REPEAT_THRESHOLD = 3  # tickets on one unit within the window, counting the current one

STOPWORDS = set("""a an and are as at be but by can do does for from has have i in is it its it's
just kind of on or our out really so some the their them then there this to too up very was were
what when with won't not no keeps keep getting get coming come anymore one all any every""".split())


def words(value: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", value.lower()) if w not in STOPWORDS and len(w) > 1]


def stem(word: str) -> str:
    """A tiny stemmer so "leaking", "leaks" and "leak" compare equal."""
    for suffix in ("ing", "ers", "er", "ed", "ies", "es", "s", "y"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def stems(value: str) -> set[str]:
    return {stem(w) for w in words(value)}


def fts_query(value: str) -> str:
    """An FTS5 OR-query of the meaningful words, quoted so punctuation can't break the syntax."""
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words(value))) or '""'


@dataclass
class IssueMatch:
    stat: IssueStat
    product: Product
    match: float  # share of the issue's symptom words found in the report
    score: float


@dataclass
class Context:
    company: Company
    ticket: Ticket
    site: Site
    asset: Asset | None
    product: Product | None
    products: list[Product]  # the known model, or all models at the site when unknown
    query_text: str
    manual: list[ManualChunk] = field(default_factory=list)
    issues: list[IssueMatch] = field(default_factory=list)
    similar: list[tuple[Ticket, KnownIssue | None]] = field(default_factory=list)
    asset_history: list[tuple[Ticket, KnownIssue | None]] = field(default_factory=list)
    parts: dict[str, Part] = field(default_factory=dict)
    repeat_count: int = 0

    @property
    def repeat_failure(self) -> bool:
        return self.repeat_count >= REPEAT_THRESHOLD


def build_context(session: Session, ticket: Ticket, extra_text: str = "") -> Context:
    company = session.get(Company, ticket.company_id)
    site = session.get(Site, ticket.site_id)
    asset = session.get(Asset, ticket.asset_id) if ticket.asset_id else None
    product = session.get(Product, ticket.product_id) if ticket.product_id else None
    if product:
        products = [product]
    else:
        products = list(session.exec(select(Product).join(Asset, Asset.product_id == Product.id)
                                     .where(Asset.site_id == site.id).distinct()))
    product_ids = [p.id for p in products]
    query_text = f"{ticket.description} {extra_text}".strip()
    ctx = Context(company=company, ticket=ticket, site=site, asset=asset, product=product,
                  products=products, query_text=query_text)

    # Manual sections, best keyword match first.
    if product_ids:
        rows = session.execute(text(
            "SELECT chunk_id FROM manual_chunks_fts WHERE manual_chunks_fts MATCH :q AND company_id = :c "
            f"AND product_id IN ({','.join(str(i) for i in product_ids)}) ORDER BY bm25(manual_chunks_fts) LIMIT 6"),
            {"q": fts_query(query_text), "c": company.id}).all()
        ctx.manual = [session.get(ManualChunk, r[0]) for r in rows]

    # Known issues: how well the report matches the symptoms, plus how common the issue is lately.
    by_id = {p.id: p for p in products}
    report = stems(query_text)
    matches = []
    for stat in issue_stats(session, company.id, product_ids).values():
        issue = stat.issue
        symptom_words = stems(f"{issue.title} {issue.symptoms}")
        overlap = len(report & symptom_words)
        match = overlap / max(len(report), 1)
        score = 3 * overlap + min(stat.weighted, 4) * 0.5 + (1 if stat.trend == "rising" else 0)
        matches.append(IssueMatch(stat=stat, product=by_id[issue.product_id], match=match, score=score))
    ctx.issues = sorted(matches, key=lambda m: -m.score)

    # Similar resolved tickets for the same model(s).
    if product_ids:
        rows = session.execute(text(
            "SELECT ticket_id FROM tickets_fts WHERE tickets_fts MATCH :q AND company_id = :c "
            f"AND product_id IN ({','.join(str(i) for i in product_ids)}) ORDER BY bm25(tickets_fts) LIMIT 12"),
            {"q": fts_query(query_text), "c": company.id}).all()
        for (ticket_id,) in rows:
            past = session.get(Ticket, ticket_id)
            if past and past.id != ticket.id and past.closed_at and len(ctx.similar) < 5:
                ctx.similar.append((past, session.get(KnownIssue, past.known_issue_id) if past.known_issue_id else None))

    # This unit's own history, newest first.
    if asset:
        since = today() - timedelta(days=180)
        history = session.exec(select(Ticket).where(Ticket.asset_id == asset.id, Ticket.id != ticket.id)
                               .order_by(Ticket.created_at.desc())).all()
        for past in history:
            if past.created_at.date() >= since:
                ctx.asset_history.append((past, session.get(KnownIssue, past.known_issue_id) if past.known_issue_id else None))
        window_start = ticket.created_at.date() - timedelta(days=REPEAT_WINDOW_DAYS)
        ctx.repeat_count = 1 + sum(1 for past, _ in ctx.asset_history if past.created_at.date() >= window_start)

    # Parts that fit these models.
    refs = {p.ref for p in products}
    for part in session.exec(select(Part).where(Part.company_id == company.id)):
        if refs & set(part.compatible_model_refs or []):
            ctx.parts[part.ref] = part
    return ctx
