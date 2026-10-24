"""The "Log in as" picker: a cookie holding the chosen user's id. No real authentication.

Pages depend on `require_login`, which returns the current user and their
company, or redirects to the picker if nobody is chosen yet.
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.db import get_session
from app.models import Company, User

COOKIE_NAME = "techmind_user"


@dataclass
class Current:
    user: User
    company: Company

    @property
    def is_manager(self) -> bool:
        return self.user.role == "manager"


def current_user(request: Request, session: Session) -> User | None:
    raw = request.cookies.get(COOKIE_NAME, "")
    return session.get(User, int(raw)) if raw.isdigit() else None


def require_login(request: Request, session: Session = Depends(get_session)) -> Current:
    user = current_user(request, session)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return Current(user=user, company=session.get(Company, user.company_id))


def display_name(user: User) -> str:
    return user.name if user.role == "manager" else f"Tech: {user.name}"
