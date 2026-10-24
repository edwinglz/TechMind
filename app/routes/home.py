"""Home page: an overview of the logged-in user's company and its imported data."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, func, select

from app.auth import Current, require_login
from app.db import get_session
from app.models import Asset, KnownIssue, ManualChunk, Part, Product, Site, Ticket
from app.templating import render

router = APIRouter()


def _count(session: Session, model, company_id: int, *where) -> int:
    query = select(func.count()).select_from(model).where(model.company_id == company_id, *where)
    return session.exec(query).one()


@router.get("/")
def home(request: Request, cur: Current = Depends(require_login), session: Session = Depends(get_session)):
    cid = cur.company.id
    tickets = _count(session, Ticket, cid)
    self_fixed = _count(session, Ticket, cid, Ticket.resolved_by_reporter == True)  # noqa: E712
    stats = {
        "sites": _count(session, Site, cid),
        "assets": _count(session, Asset, cid),
        "products": _count(session, Product, cid),
        "parts": _count(session, Part, cid),
        "issues": _count(session, KnownIssue, cid),
        "manual_sections": _count(session, ManualChunk, cid),
        "tickets": tickets,
        "self_fix_share": round(100 * self_fixed / tickets) if tickets else 0,
    }
    return render(request, "home.html", user=cur.user, company=cur.company, stats=stats)


@router.get("/healthz")
def healthz():
    return {"ok": True}
