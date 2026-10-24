"""Log in with username and password, and log out."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.auth import COOKIE_NAME, current_user, session_cookie_value, verify_password
from app.db import get_session
from app.models import User
from app.templating import render

router = APIRouter()


@router.get("/login")
def login_page(request: Request, session: Session = Depends(get_session)):
    if current_user(request, session):
        return RedirectResponse("/app", status_code=303)
    return render(request, "login.html")


@router.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""),
          session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == username.strip().lower())).first()
    if user is None or not verify_password(password, user.password_hash):
        # Same message either way, so the page doesn't reveal which usernames exist.
        return render(request, "login.html", status_code=401, error="Wrong username or password.",
                      username=username)
    response = RedirectResponse("/app", status_code=303)
    response.set_cookie(COOKIE_NAME, session_cookie_value(user.id), httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
