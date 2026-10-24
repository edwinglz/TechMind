"""End-to-end: front page, login with username/password, and the manager board."""

import pytest
from fastapi.testclient import TestClient

from app.auth import COOKIE_NAME, hash_password, verify_password
from app.main import app

PASSWORD = "test-password"  # set in conftest.py


@pytest.fixture()
def client():
    with TestClient(app) as c:  # "with" runs startup, which seeds the database
        yield c


def _login(client, username, password=PASSWORD):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_front_page_is_public_and_company_neutral(client):
    page = client.get("/").text
    assert "Know what's broken before the truck rolls" in page
    assert 'action="/login"' in page
    # The product page must not expose any customer's data.
    assert "Kestrel" not in page and "Store #" not in page


def test_app_requires_login(client):
    response = client.get("/app", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_wrong_password_is_rejected(client):
    response = _login(client, "manager", "nope")
    assert response.status_code == 401
    assert "Wrong username or password" in response.text
    assert COOKIE_NAME not in response.cookies
    assert _login(client, "nobody").status_code == 401


def test_manager_login_shows_service_board(client):
    response = _login(client, "Manager ")  # usernames ignore case and surrounding spaces
    assert response.status_code == 303 and response.headers["location"] == "/app"
    page = client.get("/app").text
    assert "Kestrel Burger Co." in page
    assert "Service board" in page and "Needs a decision" in page and "Store staff trying a fix" in page
    # Logged-in visitors skip the front page.
    assert client.get("/", follow_redirects=False).headers["location"] == "/app"


def test_technician_login(client):
    _login(client, "ana")
    page = client.get("/app").text
    assert "Tech: Ana" in page and "My jobs" in page


def test_logout(client):
    _login(client, "luis")
    response = client.post("/logout", follow_redirects=False)
    assert response.headers["location"] == "/"
    client.cookies.clear()
    assert client.get("/app", follow_redirects=False).status_code == 303


def test_forged_cookie_is_ignored(client):
    client.cookies.set(COOKIE_NAME, "1.not-a-real-signature")
    assert client.get("/app", follow_redirects=False).status_code == 303
    client.cookies.set(COOKIE_NAME, "1")
    assert client.get("/app", follow_redirects=False).status_code == 303


def test_password_hashing():
    stored = hash_password("s3cret")
    assert "s3cret" not in stored
    assert verify_password("s3cret", stored)
    assert not verify_password("S3cret", stored)
    assert not verify_password("s3cret", "garbage")


def test_healthz(client):
    assert client.get("/healthz").json() == {"ok": True}
