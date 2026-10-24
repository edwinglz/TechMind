"""Write a validated ImportBundle into the database as a new company.

Besides copying rows, loading does three things worth knowing about:
- Manuals are split into sections and added to the full-text search index.
- Each known issue's documented fix becomes its first fix variant.
- Imported ticket history is grouped into fix variants: every distinct set of
  fix steps used for an issue becomes a variant, so the success rates of
  alternative fixes are known from day one.
"""

from datetime import datetime, time, timedelta

from sqlmodel import Session

from app.importer.manuals import split_markdown
from app.importer.parse import ImportBundle
from app.models import (Asset, Company, FixVariant, KnownIssue, ManualChunk, Part, Product, Site,
                        Ticket, TicketStatus)
from app.services.fix_variants import normalize_steps
from app.services.search import index_manual_chunk, index_ticket


def _add(session: Session, obj):
    """Insert a row and return it with its new id."""
    session.add(obj)
    session.flush()
    return obj


def load_company(session: Session, bundle: ImportBundle, company_name: str | None = None) -> Company:
    """Create a company from a bundle. The caller commits (or rolls back) the session.

    User accounts are not part of the import format; the caller creates them.
    """
    if not bundle.ok:
        raise ValueError("Import has errors: " + "; ".join(bundle.all_errors()))

    rows = bundle.rows
    name = (company_name or bundle.profile.get("company_name") or "New company").strip()
    company = _add(session, Company(name=name, profile=bundle.profile, **bundle.settings))
    cid = company.id

    site_ids = {}
    for r in rows["sites.csv"]:
        site = _add(session, Site(company_id=cid, ref=r["site_id"], name=r["name"],
                                  address=r["address"], region=r["region"]))
        site_ids[r["site_id"]] = site.id

    product_ids = {}
    for r in rows["products.csv"]:
        product = _add(session, Product(company_id=cid, ref=r["model_id"], manufacturer=r["manufacturer"],
                                        model_name=r["model_name"], category=r["category"],
                                        manual_file=r["manual_file"]))
        product_ids[r["model_id"]] = product.id
        manual = bundle.manuals.get(r["manual_file"])
        if manual:
            for position, section in enumerate(split_markdown(manual)):
                chunk = _add(session, ManualChunk(company_id=cid, product_id=product.id,
                                                  manual_file=r["manual_file"], position=position,
                                                  section_title=section.title, content=section.content))
                index_manual_chunk(session, chunk)

    asset_ids = {}
    for r in rows["assets.csv"]:
        asset = _add(session, Asset(company_id=cid, ref=r["asset_id"], product_id=product_ids[r["model_id"]],
                                    site_id=site_ids[r["site_id"]], serial=r["serial"],
                                    install_date=r["install_date"], last_service_date=r["last_service_date"]))
        asset_ids[r["asset_id"]] = asset.id

    for r in rows["parts.csv"]:
        session.add(Part(company_id=cid, ref=r["part_id"], name=r["name"],
                         compatible_model_refs=r["compatible_models"], unit_price=r["unit_price"],
                         in_stock=r["in_stock"]))

    issue_ids = {}
    # variants[issue id][normalized steps] -> FixVariant, used to group history below
    variants: dict[int, dict[tuple, FixVariant]] = {}
    for r in rows["known_issues.csv"]:
        issue = _add(session, KnownIssue(company_id=cid, ref=r["issue_id"], product_id=product_ids[r["model_id"]],
                                         title=r["title"], symptoms=r["symptoms"], root_cause=r["root_cause"],
                                         part_refs=r["part_ids"], avg_minutes=r["avg_minutes"],
                                         reporter_fixable=r["reporter_fixable"]))
        issue_ids[r["issue_id"]] = issue.id
        variants[issue.id] = {}
        if r["fix_steps"]:
            variant = _add(session, FixVariant(company_id=cid, known_issue_id=issue.id,
                                               steps=r["fix_steps"], source="import"))
            variants[issue.id][normalize_steps(r["fix_steps"])] = variant

    # Oldest first, so a variant's created_at is the first time that fix was used.
    for r in sorted(rows["ticket_history.csv"], key=lambda t: (t["date"], t["ticket_id"])):
        opened = datetime.combine(r["date"], time(9, 0))
        issue_id = issue_ids.get(r["issue_id"])
        variant_id = None
        # Fixes done by the reporter over the phone don't count toward variant
        # stats: they say how common an issue is, not how well a technician fix works.
        if issue_id and r["fix_steps_used"] and not r["resolved_by_reporter"]:
            key = normalize_steps(r["fix_steps_used"])
            variant = variants[issue_id].get(key)
            if variant is None:
                variant = _add(session, FixVariant(company_id=cid, known_issue_id=issue_id,
                                                   steps=r["fix_steps_used"], source="history",
                                                   created_at=opened))
                variants[issue_id][key] = variant
            variant_id = variant.id

        ticket = _add(session, Ticket(
            company_id=cid, ref=r["ticket_id"], site_id=site_ids[r["site_id"]],
            asset_id=asset_ids.get(r["asset_id"]), product_id=product_ids.get(r["model_id"]),
            description=r["reported_description"],
            service_mode="remote" if r["resolved_by_reporter"] else "onsite",
            status=TicketStatus.CLOSED, source="imported",
            created_at=opened, closed_at=opened + timedelta(minutes=r["minutes"] or 0),
            known_issue_id=issue_id, fix_variant_id=variant_id,
            fix_description="|".join(r["fix_steps_used"]) or None,
            part_refs=r["part_ids"], minutes=r["minutes"], resolved=r["resolved"],
            resolved_by_reporter=r["resolved_by_reporter"],
        ))
        index_ticket(session, ticket)

    return company
