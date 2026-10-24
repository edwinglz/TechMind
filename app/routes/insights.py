"""What the company's repair history says: trends, best fixes, repeat failures,
trips avoided, the full ticket history, and a CSV export in the import format."""

import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, func, select

from app.auth import Current, require_login
from app.config import today
from app.db import get_session
from app.models import Asset, KnownIssue, Product, Site, Ticket
from app.services.insights import dispatch_savings, issue_stats, stats_by_product
from app.templating import render

router = APIRouter(prefix="/app")


def _manager(cur: Current) -> None:
    if not cur.is_manager:
        raise HTTPException(403)


@router.get("/insights")
def insights(request: Request, cur: Current = Depends(require_login), session: Session = Depends(get_session)):
    _manager(cur)
    cid = cur.company.id
    stats = issue_stats(session, cid)
    products = session.exec(select(Product).where(Product.company_id == cid).order_by(Product.category)).all()
    grouped = stats_by_product(stats)
    for issues in grouped.values():
        issues.sort(key=lambda s: -s.weighted)

    # Units with 3+ tickets in the last 60 days.
    since = today() - timedelta(days=60)
    counts = session.exec(select(Ticket.asset_id, func.count(Ticket.id)).where(
        Ticket.company_id == cid, Ticket.asset_id.is_not(None), Ticket.created_at >= since)
        .group_by(Ticket.asset_id)).all()
    repeat = []
    for asset_id, n in sorted(counts, key=lambda r: -r[1]):
        if n >= 3:
            asset = session.get(Asset, asset_id)
            repeat.append({"asset": asset, "n": n, "site": session.get(Site, asset.site_id),
                           "product": session.get(Product, asset.product_id)})

    # How often the brief's top cause matched what the technician found (tickets closed in the app).
    from app.services.brief import latest_brief
    checked = hits = 0
    for t in session.exec(select(Ticket).where(Ticket.company_id == cid, Ticket.source == "app",
                                               Ticket.known_issue_id.is_not(None))):
        brief = latest_brief(session, t.id)
        if brief and brief.data.get("probable_causes"):
            issue = session.get(KnownIssue, t.known_issue_id)
            checked += 1
            hits += brief.data["probable_causes"][0].get("issue_id") == issue.ref

    avoided, saved = dispatch_savings(session, cur.company)
    total = session.exec(select(func.count(Ticket.id)).where(Ticket.company_id == cid)).one()
    return render(request, "insights.html", user=cur.user, company=cur.company, nav="insights",
                  products=products, grouped=grouped, repeat=repeat, avoided=avoided, saved=saved,
                  total=total, checked=checked, hits=hits,
                  rising=sorted((s for s in stats.values() if s.trend == "rising"), key=lambda s: -s.last30),
                  fading=sorted((s for s in stats.values() if s.trend == "fading"), key=lambda s: -s.prior30))


@router.get("/history")
def history(request: Request, cur: Current = Depends(require_login), session: Session = Depends(get_session)):
    _manager(cur)
    cid = cur.company.id
    tickets = session.exec(select(Ticket).where(Ticket.company_id == cid).order_by(Ticket.created_at.desc())).all()
    sites = {s.id: s for s in session.exec(select(Site).where(Site.company_id == cid))}
    products = {p.id: p for p in session.exec(select(Product).where(Product.company_id == cid))}
    issues = {i.id: i for i in session.exec(select(KnownIssue).where(KnownIssue.company_id == cid))}
    return render(request, "history.html", user=cur.user, company=cur.company, nav="history", tickets=tickets,
                  sites=sites, products=products, issues=issues)


@router.get("/export/ticket_history.csv")
def export_history(cur: Current = Depends(require_login), session: Session = Depends(get_session)):
    """Closed tickets in the same format as ticket_history.csv, so the company keeps its updated data."""
    _manager(cur)
    cid = cur.company.id
    sites = {s.id: s.ref for s in session.exec(select(Site).where(Site.company_id == cid))}
    assets = {a.id: a.ref for a in session.exec(select(Asset).where(Asset.company_id == cid))}
    products = {p.id: p.ref for p in session.exec(select(Product).where(Product.company_id == cid))}
    issues = {i.id: i.ref for i in session.exec(select(KnownIssue).where(KnownIssue.company_id == cid))}
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ticket_id", "date", "site_id", "asset_id", "model_id", "reported_description", "issue_id",
                     "fix_steps_used", "part_ids", "minutes", "resolved", "resolved_by_reporter"])
    for t in session.exec(select(Ticket).where(Ticket.company_id == cid, Ticket.closed_at.is_not(None))
                          .order_by(Ticket.created_at)):
        writer.writerow([t.ref, t.created_at.date().isoformat(), sites.get(t.site_id, ""), assets.get(t.asset_id, ""),
                         products.get(t.product_id, ""), t.description, issues.get(t.known_issue_id, ""),
                         t.fix_description or "", ";".join(t.part_refs or []), t.minutes or "",
                         "y" if t.resolved else "n", "y" if t.resolved_by_reporter else "n"])
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=ticket_history.csv"})
