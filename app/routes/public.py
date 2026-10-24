"""The public product page at "/". It describes TechMind itself, not any customer company."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.auth import current_user
from app.db import get_session
from app.templating import render

router = APIRouter()


@router.get("/")
def landing(request: Request, session: Session = Depends(get_session)):
    # Logged-in visitors see "Open TechMind" instead of "Log in".
    return render(request, "landing.html", logged_in=current_user(request, session) is not None)


@router.get("/healthz")
def healthz():
    return {"ok": True}
