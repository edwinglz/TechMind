"""Login with username and password, kept deliberately small.

- Passwords are stored as salted PBKDF2 hashes (Python standard library), never in plain text.
- After login, the browser holds a cookie with the user id plus an HMAC signature
  made with SECRET_KEY. Without the key nobody can forge a cookie for another user.
- Pages depend on `require_login`, which returns the current user and their
  company, or redirects to the login page.

This is demo-grade auth (no sign-up, password reset, or rate limiting); real
authentication is out of scope for the hackathon.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.models import Company, User

COOKIE_NAME = "techmind_session"
PBKDF2_ITERATIONS = 200_000


# ---------- passwords ----------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), expected)


# ---------- session cookie ----------

def _signature(user_id: int) -> str:
    return hmac.new(settings.secret_key.encode(), f"user:{user_id}".encode(), hashlib.sha256).hexdigest()


def session_cookie_value(user_id: int) -> str:
    return f"{user_id}.{_signature(user_id)}"


def _user_id_from_cookie(value: str) -> int | None:
    user_id, _, signature = value.partition(".")
    if not user_id.isdigit() or not hmac.compare_digest(signature, _signature(int(user_id))):
        return None
    return int(user_id)


# ---------- request helpers ----------

@dataclass
class Current:
    user: User
    company: Company

    @property
    def is_manager(self) -> bool:
        return self.user.role == "manager"


def current_user(request: Request, session: Session) -> User | None:
    user_id = _user_id_from_cookie(request.cookies.get(COOKIE_NAME, ""))
    return session.get(User, user_id) if user_id else None


def require_login(request: Request, session: Session = Depends(get_session)) -> Current:
    user = current_user(request, session)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return Current(user=user, company=session.get(Company, user.company_id))


def display_name(user: User) -> str:
    return user.name if user.role == "manager" else f"Tech: {user.name}"
