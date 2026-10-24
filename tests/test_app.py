"""End-to-end: the app starts, seeds the demo company, and the login + home pages work."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # "with" runs startup, which seeds the database
        yield c


def _login(client, name):
    page = client.get("/login").text
    # Find the hidden user_id input that follows this user's button.
    marker = page.index(f">{name}<")
    start = page.rindex('name="user_id" value="', 0, marker) + len('name="user_id" value="')
    user_id = page[start:page.index('"', start)]
    client.post("/login", data={"user_id": user_id}, follow_redirects=False)


def test_home_redirects_to_login_when_logged_out(client):
    client.cookies.clear()
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_lists_demo_users(client):
    page = client.get("/login").text
    for name in ("Kestrel Burger Co.", "Manager", "Tech: Ana", "Tech: Luis"):
        assert name in page


def test_home_uses_company_labels(client):
    _login(client, "Manager")
    page = client.get("/").text
    assert "Kestrel Burger Co." in page
    assert "Stores" in page and "Machines" in page and "Fixed by store staff" in page
    assert "30%" in page
    assert "$95.00" in page


def test_healthz(client):
    assert client.get("/healthz").json() == {"ok": True}
