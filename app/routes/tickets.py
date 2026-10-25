"""Ticket pages: the manager's board, report intake, the ticket with its brief,
and every action on it (self-fix, dispatch, questions, refine, chat, close).

Actions are HTMX requests. Most return the refreshed ticket body (header,
brief and side panel) so the page always shows the current state; chat and
question answers return only their own panel so typing and open sections are
not disturbed.
"""

import asyncio
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from app.auth import Current, require_login
from app.config import settings
from app.db import get_session
from app.models import (Asset, KnownIssue, Part, Product, Site, Ticket, TicketEvent, TicketStatus,
                        User)
from app.services import brief as brief_service
from app.services import tickets as svc
from app.services.insights import issue_stats
from app.templating import labels_for, render, status_info

router = APIRouter(prefix="/app")

MOCK_DELAY = float(os.getenv("MOCK_DELAY_SECONDS", "1.6"))  # lets the "preparing" steps play in mock mode


# ---------- helpers ----------

def _ticket_or_404(session: Session, cur: Current, ticket_id: int) -> Ticket:
    ticket = session.get(Ticket, ticket_id)
    if not ticket or ticket.company_id != cur.company.id:
        raise HTTPException(404)
    if not cur.is_manager and ticket.assigned_user_id != cur.user.id:
        raise HTTPException(403, "This job isn't assigned to you.")
    return ticket


def _card(session: Session, ticket: Ticket) -> dict:
    """Everything a ticket tag on the board needs."""
    site = session.get(Site, ticket.site_id)
    product = session.get(Product, ticket.product_id) if ticket.product_id else None
    asset = session.get(Asset, ticket.asset_id) if ticket.asset_id else None
    tech = session.get(User, ticket.assigned_user_id) if ticket.assigned_user_id else None
    brief = brief_service.latest_brief(session, ticket.id)
    top = brief.data["probable_causes"][0]["cause"] if brief and brief.data.get("probable_causes") else None
    return {"t": ticket, "site": site, "product": product, "asset": asset, "tech": tech, "top": top,
            "repeat": bool(brief and brief.data.get("context", {}).get("repeat_failure"))}


def _body_context(session: Session, cur: Current, ticket: Ticket) -> dict:
    site = session.get(Site, ticket.site_id)
    asset = session.get(Asset, ticket.asset_id) if ticket.asset_id else None
    product = session.get(Product, ticket.product_id) if ticket.product_id else None
    brief = brief_service.latest_brief(session, ticket.id)
    events = session.exec(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)
                          .order_by(TicketEvent.created_at)).all()
    users = {u.id: u for u in session.exec(select(User).where(User.company_id == cur.company.id))}
    technicians = [u for u in users.values() if u.role == "technician"]
    self_fix_tries = [e for e in events if e.type == "self_fix_outcome"]
    return {"ticket": ticket, "site": site, "asset": asset, "product": product, "brief": brief,
            "events": events, "users": users, "technicians": technicians,
            "tech": users.get(ticket.assigned_user_id), "self_fix_tries": self_fix_tries,
            "status": status_info(ticket, labels_for(cur.company)), "is_manager": cur.is_manager}


def _body(request: Request, session: Session, cur: Current, ticket: Ticket):
    return render(request, "partials/ticket_body.html", user=cur.user, company=cur.company,
                  **_body_context(session, cur, ticket))


# ---------- board / my jobs ----------

@router.get("")
def home(request: Request, cur: Current = Depends(require_login), session: Session = Depends(get_session)):
    cid = cur.company.id
    labels = labels_for(cur.company)
    if not cur.is_manager:
        mine = session.exec(select(Ticket).where(Ticket.company_id == cid, Ticket.assigned_user_id == cur.user.id)
                            .order_by(Ticket.created_at.desc())).all()
        open_jobs = [_card(session, t) for t in mine if t.status != TicketStatus.CLOSED]
        done = [_card(session, t) for t in mine if t.status == TicketStatus.CLOSED][:5]
        return render(request, "jobs.html", user=cur.user, company=cur.company, open_jobs=open_jobs, done=done,
                      nav="board")

    app_tickets = session.exec(select(Ticket).where(Ticket.company_id == cid, Ticket.source == "app")
                               .order_by(Ticket.created_at.desc())).all()
    lanes = {"decide": [], "staff": [], "tech": [], "closed": []}
    for t in app_tickets:
        lane = status_info(t, labels)["lane"]
        if lane != "closed" or len(lanes["closed"]) < 6:
            lanes[lane].append(_card(session, t))

    # Signals from history, shown under the board.
    stats = issue_stats(session, cid)
    products = {p.id: p for p in session.exec(select(Product).where(Product.company_id == cid))}
    rising = sorted((s for s in stats.values() if s.trend == "rising"), key=lambda s: -s.last30)[:4]
    changed = [s for s in stats.values() if s.recommended_changed][:4]
    from app.services.insights import dispatch_savings
    avoided, saved = dispatch_savings(session, cur.company)
    return render(request, "board.html", user=cur.user, company=cur.company, lanes=lanes, rising=rising,
                  changed=changed, products=products, avoided=avoided, saved=saved, nav="board")


# ---------- intake ----------

@router.get("/tickets/new")
def new_ticket(request: Request, cur: Current = Depends(require_login), session: Session = Depends(get_session)):
    if not cur.is_manager:
        raise HTTPException(403)
    sites = session.exec(select(Site).where(Site.company_id == cur.company.id).order_by(Site.ref)).all()
    return render(request, "new_ticket.html", user=cur.user, company=cur.company, sites=sites, nav="new")


@router.get("/site-assets", response_class=HTMLResponse)
def site_assets(request: Request, site_id: int = 0, cur: Current = Depends(require_login),
                session: Session = Depends(get_session)):
    rows = session.exec(select(Asset, Product).join(Product, Asset.product_id == Product.id)
                        .where(Asset.site_id == site_id, Asset.company_id == cur.company.id)
                        .order_by(Product.category, Asset.ref)).all()
    return render(request, "partials/asset_options.html", company=cur.company, rows=rows)


@router.get("/asset-card", response_class=HTMLResponse)
def asset_card(request: Request, asset_id: str = "", cur: Current = Depends(require_login),
               session: Session = Depends(get_session)):
    asset = session.get(Asset, int(asset_id)) if asset_id.isdigit() else None
    if not asset or asset.company_id != cur.company.id:
        return render(request, "partials/asset_card.html", company=cur.company, asset=None)
    return render(request, "partials/asset_card.html", company=cur.company, **_asset_context(session, asset))


def _asset_context(session: Session, asset: Asset) -> dict:
    product = session.get(Product, asset.product_id)
    site = session.get(Site, asset.site_id)
    history = session.exec(select(Ticket).where(Ticket.asset_id == asset.id).order_by(Ticket.created_at.desc())).all()
    issues = {i.id: i for i in session.exec(select(KnownIssue).where(KnownIssue.product_id == product.id))}
    return {"asset": asset, "product": product, "site": site, "history": history, "issues": issues}


@router.post("/tickets")
async def create_ticket(request: Request, site_id: int = Form(...), asset_id: str = Form(""),
                        description: str = Form(...), service_mode: str = Form("onsite"),
                        photo: UploadFile | None = File(None), cur: Current = Depends(require_login),
                        session: Session = Depends(get_session)):
    if not cur.is_manager:
        raise HTTPException(403)
    site = session.get(Site, site_id)
    if not site or site.company_id != cur.company.id or not description.strip():
        raise HTTPException(400, "Pick a site and describe the problem.")
    asset = session.get(Asset, int(asset_id)) if asset_id.isdigit() else None
    photo_path = None
    if photo is not None and photo.filename:
        suffix = Path(photo.filename).suffix.lower()
        if suffix in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"):
            name = f"{secrets.token_hex(8)}{suffix}"
            target = settings.upload_dir / name
            target.write_bytes(await photo.read())
            photo_path = str(target)
    ticket = svc.create(session, company_id=cur.company.id, site_id=site.id, asset_id=asset.id if asset else None,
                        product_id=asset.product_id if asset else None, description=description,
                        service_mode="remote" if service_mode == "remote" else "onsite", photo_path=photo_path,
                        actor_id=cur.user.id)
    session.commit()
    return RedirectResponse(f"/app/tickets/{ticket.id}", status_code=303)


# ---------- the ticket ----------

@router.get("/tickets/{ticket_id}")
def ticket_page(request: Request, ticket_id: int, cur: Current = Depends(require_login),
                session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    return render(request, "ticket.html", user=cur.user, company=cur.company, nav="board",
                  **_body_context(session, cur, ticket))


@router.post("/tickets/{ticket_id}/brief", response_class=HTMLResponse)
async def make_brief(request: Request, ticket_id: int, cur: Current = Depends(require_login),
                     session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    if brief_service.latest_brief(session, ticket.id) is None:
        if settings.ai_mode == "mock" and MOCK_DELAY:
            await asyncio.sleep(MOCK_DELAY)
        brief_service.generate(session, ticket, cur.user.id)
        if ticket.status == TicketStatus.NEW:
            ticket.status = TicketStatus.BRIEFED
        session.commit()
    return _body(request, session, cur, ticket)


@router.post("/tickets/{ticket_id}/refine", response_class=HTMLResponse)
async def refine(request: Request, ticket_id: int, cur: Current = Depends(require_login),
                 session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    if settings.ai_mode == "mock" and MOCK_DELAY:
        await asyncio.sleep(MOCK_DELAY / 2)
    brief_service.generate(session, ticket, cur.user.id, refine=True)
    session.commit()
    return _body(request, session, cur, ticket)


@router.post("/tickets/{ticket_id}/answer", response_class=HTMLResponse)
def answer(request: Request, ticket_id: int, question: str = Form(...), answer: str = Form(""),
           kind: str = Form("yes_no"), note: str = Form(""), cur: Current = Depends(require_login),
           session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    answer = answer.strip()[:200]
    if kind == "reading":
        value = answer or "clear"  # an empty box clears the reading
    else:
        current = (ticket.answers or {}).get(question, {}).get("answer")
        value = "clear" if current == answer else answer  # tapping the chosen answer again un-selects it
    svc.save_answer(session, ticket, cur.user.id, question, value, note)
    session.commit()
    brief = brief_service.latest_brief(session, ticket.id)
    return render(request, "partials/questions.html", user=cur.user, company=cur.company, ticket=ticket, brief=brief)


@router.post("/tickets/{ticket_id}/self-fix", response_class=HTMLResponse)
def approve_self_fix(request: Request, ticket_id: int, cur: Current = Depends(require_login),
                     session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    brief = brief_service.latest_brief(session, ticket.id)
    fix = brief.data["reporter_self_fix"] if brief else {}
    svc.approve_self_fix(session, ticket, cur.user.id, fix.get("steps", []), fix.get("targets", []))
    session.commit()
    return _body(request, session, cur, ticket)


@router.post("/tickets/{ticket_id}/self-fix/outcome", response_class=HTMLResponse)
async def self_fix_outcome(request: Request, ticket_id: int, resolved: str = Form(...), note: str = Form(""),
                           cur: Current = Depends(require_login), session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    svc.record_self_fix_outcome(session, ticket, cur.user.id, resolved == "yes", note)
    if resolved != "yes":
        # What the reporter tried rules causes out, so re-rank right away.
        brief_service.generate(session, ticket, cur.user.id, refine=True)
    session.commit()
    return _body(request, session, cur, ticket)


@router.post("/tickets/{ticket_id}/assign", response_class=HTMLResponse)
def assign(request: Request, ticket_id: int, technician_id: int = Form(...), cur: Current = Depends(require_login),
           session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    tech = session.get(User, technician_id)
    if not tech or tech.company_id != cur.company.id:
        raise HTTPException(400)
    svc.assign(session, ticket, cur.user.id, tech)
    session.commit()
    return _body(request, session, cur, ticket)


@router.get("/tickets/{ticket_id}/chat", response_class=HTMLResponse)
def chat_log(request: Request, ticket_id: int, cur: Current = Depends(require_login),
             session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    return _chat(request, session, cur, ticket)


@router.post("/tickets/{ticket_id}/chat", response_class=HTMLResponse)
def chat_send(request: Request, ticket_id: int, text: str = Form(""), cur: Current = Depends(require_login),
              session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    if text.strip():
        svc.log_event(session, ticket, "chat_message", cur.user.id, text=text.strip()[:1000])
        session.commit()
    return _chat(request, session, cur, ticket)


def _chat(request, session, cur, ticket):
    messages = session.exec(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id,
                                                      TicketEvent.type == "chat_message")
                            .order_by(TicketEvent.created_at)).all()
    users = {u.id: u for u in session.exec(select(User).where(User.company_id == cur.company.id))}
    return render(request, "partials/chat_log.html", user=cur.user, company=cur.company, ticket=ticket,
                  messages=messages, users=users)


# ---------- close ----------

@router.get("/tickets/{ticket_id}/close")
def close_form(request: Request, ticket_id: int, cur: Current = Depends(require_login),
               session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    ctx = _body_context(session, cur, ticket)
    product_ids = [ticket.product_id] if ticket.product_id else None
    brief = ctx["brief"]
    top_ref = brief.data["probable_causes"][0]["issue_id"] if brief and brief.data["probable_causes"] else None
    # The brief's top cause first, then the most common issues.
    stats = sorted(issue_stats(session, cur.company.id, product_ids).values(),
                   key=lambda s: (s.issue.ref != top_ref, -s.last90, s.issue.title))
    parts = session.exec(select(Part).where(Part.company_id == cur.company.id)).all()
    if ticket.product_id:
        ref = ctx["product"].ref
        parts = [p for p in parts if ref in (p.compatible_model_refs or [])]
    return render(request, "close.html", user=cur.user, company=cur.company, stats=stats, top_ref=top_ref,
                  parts=parts, nav="board", **ctx)


@router.post("/tickets/{ticket_id}/close")
async def close(request: Request, ticket_id: int, cur: Current = Depends(require_login),
                session: Session = Depends(get_session)):
    ticket = _ticket_or_404(session, cur, ticket_id)
    form = await request.form()
    issue_choice = str(form.get("issue", ""))
    variant_choice = str(form.get(f"variant_{issue_choice}", form.get("variant", "other")))
    minutes = int(form.get("minutes") or 0)
    if not issue_choice or (issue_choice == "new" and not ticket.product_id):
        raise HTTPException(400, "Pick what was wrong.")
    svc.close(session, ticket, cur.user.id, issue_choice=issue_choice,
              new_issue_title=str(form.get("new_issue_title", "")), variant_choice=variant_choice,
              fix_description=str(form.get("fix_description", "")), part_refs=list(form.getlist("parts")),
              minutes=minutes, resolved=form.get("resolved") != "no")
    session.commit()
    return RedirectResponse(f"/app/tickets/{ticket.id}?closed=1", status_code=303)


# ---------- equipment ----------

@router.get("/assets/{asset_id}")
def asset_page(request: Request, asset_id: int, cur: Current = Depends(require_login),
               session: Session = Depends(get_session)):
    asset = session.get(Asset, asset_id)
    if not asset or asset.company_id != cur.company.id:
        raise HTTPException(404)
    return render(request, "asset.html", user=cur.user, company=cur.company, nav="insights",
                  **_asset_context(session, asset))


