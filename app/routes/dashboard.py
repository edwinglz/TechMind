"""The app's start page after login: an overview of the company's data."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, func, select

from app.auth import Current, require_login
from app.db import get_session
from app.models import Asset, KnownIssue, Product, Site, Ticket
from app.templating import render

router = APIRouter()


def _count(session: Session, model, company_id: int, *where) -> int:
    query = select(func.count()).select_from(model).where(model.company_id == company_id, *where)
    return session.exec(query).one()


@router.get("/app")
def dashboard(request: Request, cur: Current = Depends(require_login), session: Session = Depends(get_session)):
    cid = cur.company.id
    tickets = _count(session, Ticket, cid)
    self_fixed = _count(session, Ticket, cid, Ticket.resolved_by_reporter == True)  # noqa: E712
    stats = {
        "sites": _count(session, Site, cid),
        "assets": _count(session, Asset, cid),
        "products": _count(session, Product, cid),
        "issues": _count(session, KnownIssue, cid),
        "tickets": tickets,
        "self_fix_share": round(100 * self_fixed / tickets) if tickets else 0,
    }

    # Units and past tickets per product category, so the overview shows the
    # whole range of equipment rather than any single model.
    units = dict(session.exec(
        select(Product.category, func.count(Asset.id)).join(Asset, Asset.product_id == Product.id)
        .where(Product.company_id == cid).group_by(Product.category)).all())
    ticket_counts = dict(session.exec(
        select(Product.category, func.count(Ticket.id)).join(Ticket, Ticket.product_id == Product.id)
        .where(Product.company_id == cid).group_by(Product.category)).all())
    categories = sorted(
        ({"name": name, "units": units.get(name, 0), "tickets": ticket_counts.get(name, 0)}
         for name in set(units) | set(ticket_counts)),
        key=lambda c: (-c["units"], c["name"]),
    )
    return render(request, "dashboard.html", user=cur.user, company=cur.company, stats=stats,
                  categories=categories)
