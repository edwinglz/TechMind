"""Registering a new company: account + upload -> review (with fixes) -> create -> team."""

import io
import re
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.main import app
from app.models import Company, Site, User


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _sample(client) -> bytes:
    response = client.get("/register-sample.zip")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    return response.content


def _register(client, files, username="rosa", company="Copper Canyon Grill"):
    return client.post("/register", data={"company_name": company, "your_name": "Rosa", "username": username,
                                          "password": "longenough1"}, files=files)


def test_register_with_the_sample_files(client):
    page = _register(client, [("files", ("sample.zip", _sample(client), "application/zip"))]).text
    assert "Everything checks out" in page and "Create Copper Canyon Grill and log in" in page
    token = re.search(r'/register/([a-f0-9]{24})/create', page).group(1)

    response = client.post(f"/register/{token}/create", follow_redirects=False)
    assert response.headers["location"] == "/app/team?welcome=1"
    assert "Copper Canyon Grill is set up" in client.get("/app/team?welcome=1").text

    # The new company has its own copy of the data, and nobody else's tickets.
    with Session(engine) as s:
        company = s.exec(select(Company).where(Company.name == "Copper Canyon Grill")).one()
        assert len(s.exec(select(Site).where(Site.company_id == company.id)).all()) == 8
        assert s.exec(select(User).where(User.username == "rosa")).one().role == "manager"
    board = client.get("/app").text
    assert "Copper Canyon Grill" in board and "Kestrel Burger Co." not in board

    # Add a technician, who can then log in.
    page = client.post("/app/team", data={"name": "Marco", "username": "marco", "password": "longenough2"}).text
    assert "Added Marco" in page
    client.cookies.clear()
    client.post("/login", data={"username": "marco", "password": "longenough2"})
    assert "My jobs" in client.get("/app").text


def test_errors_are_shown_and_can_be_fixed(client):
    with zipfile.ZipFile(io.BytesIO(_sample(client))) as zf:
        files = {name: zf.read(name) for name in zf.namelist() if not name.endswith("/")}
    broken = files["assets.csv"].decode().replace(",S04,", ",S99,", 1).encode()
    upload = [("files", (name.split("/")[-1], data, "text/plain")) for name, data in files.items() if name != "assets.csv"]
    page = _register(client, upload + [("files", ("assets.csv", broken, "text/csv"))], username="rosa2").text
    assert "Some files need fixing" in page and "site_id &#39;S99&#39; is not in sites.csv" in page
    assert "/create" not in page
    token = re.search(r'/register/([a-f0-9]{24})/files', page).group(1)

    page = client.post(f"/register/{token}/files", files=[("files", ("assets.csv", files["assets.csv"], "text/csv"))]).text
    assert "Everything checks out" in page


def test_account_problems_are_reported(client):
    page = _register(client, [], username="manager").text
    assert "is taken" in page and "Upload your company" in page
