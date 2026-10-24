"""The "Log in as" picker and log out."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.auth import COOKIE_NAME, current_user
from app.db import get_session
from app.models import Company, User
from app.templating import render

router = APIRouter()


@router.get("/login")
def login_page(request: Request, session: Session = Depends(get_session)):
    companies = session.exec(select(Company).order_by(Company.id)).all()
    users = session.exec(select(User).order_by(User.company_id, User.id)).all()
    by_company = [(c, [u for u in users if u.company_id == c.id]) for c in companies]
    return render(request, "login.html", user=current_user(request, session), by_company=by_company)


@router.post("/login")
def login(user_id: int = Form(...), session: Session = Depends(get_session)):
    if session.get(User, user_id) is None:
        return RedirectResponse("/login", status_code=303)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE_NAME, str(user_id), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
