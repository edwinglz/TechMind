"""The front door at "/": the login page (which also pitches the product), or the app if already logged in."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import current_user
from app.db import get_session
from app.templating import render

router = APIRouter()


@router.get("/")
def landing(request: Request, session: Session = Depends(get_session)):
    if current_user(request, session):
        return RedirectResponse("/app", status_code=303)
    return render(request, "login.html")


@router.get("/healthz")
def healthz():
    return {"ok": True}
