"""The whole product loop in mock mode, following the demo script:
report -> brief -> self-fix fails -> dispatch -> questions -> refine -> close -> insights learn."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.main import app
from app.models import Asset, Brief, FixVariant, KnownIssue, Ticket, User
from app.services.insights import issue_stats

PASSWORD = "test-password"


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _login(client, username):
    client.cookies.clear()
    client.post("/login", data={"username": username, "password": PASSWORD})


def test_demo_flow(client):
    _login(client, "manager")
    with Session(engine) as s:
        asset = s.exec(select(Asset).where(Asset.ref == "A-0401")).first()
        ana = s.exec(select(User).where(User.username == "ana")).first()
        site_id, asset_id, ana_id = asset.site_id, asset.id, ana.id

    # Intake helpers.
    assert "CI-200" in client.get(f"/app/site-assets?site_id={site_id}").text
    assert "Recent tickets on this unit" in client.get(f"/app/asset-card?asset_id={asset_id}").text

    # 1. Report.
    response = client.post("/app/tickets", data={"site_id": site_id, "asset_id": asset_id, "service_mode": "remote",
                                                 "description": "Coke and Sprite are coming out flat, kind of watery"},
                           follow_redirects=False)
    assert response.status_code == 303
    ticket_id = int(response.headers["location"].rsplit("/", 1)[1])
    assert "Preparing the brief" in client.get(f"/app/tickets/{ticket_id}").text

    # 2. Brief.
    page = client.post(f"/app/tickets/{ticket_id}/brief").text
    assert "Carbonator pump failure" in page and "Repeat failure" in page
    assert "Try a fix by phone first" in page and "Ask the store staff" in page

    # 3. Self-fix approved, then it doesn't work: the brief re-ranks.
    assert "Store staff trying the fix" in client.post(f"/app/tickets/{ticket_id}/self-fix").text
    page = client.post(f"/app/tickets/{ticket_id}/self-fix/outcome", data={"resolved": "no", "note": "Tank full"}).text
    assert "already tried" in page and "Dispatch a technician" in page

    # 4. Dispatch to Ana.
    assert "Technician on it" in client.post(f"/app/tickets/{ticket_id}/assign", data={"technician_id": ana_id}).text
    client.post(f"/app/tickets/{ticket_id}/chat", data={"text": "Bring a check valve just in case"})

    # 5. Ana answers a question and refines.
    _login(client, "ana")
    assert "Bring a check valve" in client.get(f"/app/tickets/{ticket_id}/chat").text
    with Session(engine) as s:
        brief = s.exec(select(Brief).where(Brief.ticket_id == ticket_id).order_by(Brief.version.desc())).first()
        question = next(q["question"] for q in brief.data["questions_for_reporter"] if "hums" in q["question"])
    assert 'aria-pressed="true"' in client.post(f"/app/tickets/{ticket_id}/answer",
                                                data={"question": question, "answer": "yes"}).text
    page = client.post(f"/app/tickets/{ticket_id}/refine").text
    assert page.split('class="cause-title">')[1].startswith("Carbonator pump failure")
    assert "Brief v3" in page

    # 6. Close with the technician fix (strainer + check valve), which tips it to recommended.
    with Session(engine) as s:
        issue = s.exec(select(KnownIssue).where(KnownIssue.ref == "KI-CI-03")).first()
        history_fix = s.exec(select(FixVariant).where(FixVariant.known_issue_id == issue.id,
                                                      FixVariant.source == "history")).first()
        assert issue_stats(s, issue.company_id, [issue.product_id])[issue.id].recommended.variant.source == "import"
        issue_id, variant_id = issue.id, history_fix.id
    assert "Close the job" in client.get(f"/app/tickets/{ticket_id}/close").text
    response = client.post(f"/app/tickets/{ticket_id}/close", data={
        "issue": str(issue_id), f"variant_{issue_id}": str(variant_id), "parts": ["P-CHKV", "P-STRN"],
        "minutes": "40", "resolved": "yes"}, follow_redirects=False)
    assert response.status_code == 303

    with Session(engine) as s:
        ticket = s.get(Ticket, ticket_id)
        assert ticket.status == "closed" and ticket.resolved and ticket.fix_variant_id == variant_id
        stat = issue_stats(s, ticket.company_id, [ticket.product_id])[issue_id]
        assert stat.recommended.variant.id == variant_id and stat.recommended_changed

    # 7. The manager sees what changed.
    _login(client, "manager")
    page = client.get("/app/insights").text
    assert "Technician fix, now outperforming the manual" in page and "1 of 1" in page
    assert "Fixes that changed" in client.get("/app").text
    csv = client.get("/app/export/ticket_history.csv").text
    assert csv.startswith("ticket_id,date,site_id") and "Coke and Sprite" in csv


def test_self_fix_that_works_closes_without_a_trip(client):
    _login(client, "manager")
    with Session(engine) as s:
        asset = s.exec(select(Asset).where(Asset.ref == "A-0101")).first()
    response = client.post("/app/tickets", data={"site_id": asset.site_id, "asset_id": asset.id,
                                                 "description": "Diet Coke is coming out clear"}, follow_redirects=False)
    ticket_id = int(response.headers["location"].rsplit("/", 1)[1])
    client.post(f"/app/tickets/{ticket_id}/brief")
    client.post(f"/app/tickets/{ticket_id}/self-fix")
    page = client.post(f"/app/tickets/{ticket_id}/self-fix/outcome", data={"resolved": "yes"}).text
    assert "Fixed by the store staff, no trip needed" in page


def test_unknown_asset_asks_for_the_model_first(client):
    _login(client, "manager")
    with Session(engine) as s:
        asset = s.exec(select(Asset).where(Asset.ref == "A-0101")).first()
    response = client.post("/app/tickets", data={"site_id": asset.site_id, "asset_id": "",
                                                 "description": "Something is leaking water on the floor"},
                           follow_redirects=False)
    ticket_id = int(response.headers["location"].rsplit("/", 1)[1])
    page = client.post(f"/app/tickets/{ticket_id}/brief").text
    assert "Which equipment is it?" in page


def test_technicians_only_see_their_own_jobs(client):
    _login(client, "manager")
    with Session(engine) as s:
        asset = s.exec(select(Asset).where(Asset.ref == "A-0101")).first()
    response = client.post("/app/tickets", data={"site_id": asset.site_id, "asset_id": asset.id,
                                                 "description": "Ice won't come out"}, follow_redirects=False)
    ticket_id = int(response.headers["location"].rsplit("/", 1)[1])
    _login(client, "luis")
    assert client.get(f"/app/tickets/{ticket_id}").status_code == 403
    assert client.get("/app/insights").status_code == 403


def test_reading_questions_take_a_typed_answer(client):
    """Questions like "what temperature does the display show?" are answered by typing a value."""
    _login(client, "manager")
    with Session(engine) as s:
        asset = s.exec(select(Asset).where(Asset.ref == "A-0101")).first()
    response = client.post("/app/tickets", data={"site_id": asset.site_id, "asset_id": asset.id,
                                                 "description": "Drinks are warm"}, follow_redirects=False)
    ticket_id = int(response.headers["location"].rsplit("/", 1)[1])
    client.post(f"/app/tickets/{ticket_id}/brief")
    with Session(engine) as s:  # turn the first question into a reading, as live mode can
        brief = s.exec(select(Brief).where(Brief.ticket_id == ticket_id)).first()
        data = dict(brief.data)
        data["questions_for_reporter"] = [dict(data["questions_for_reporter"][0],
                                               question="What temperature does the display show?", kind="reading")]
        brief.data = data
        s.add(brief)
        s.commit()
    page = client.get(f"/app/tickets/{ticket_id}").text
    assert 'name="kind" value="reading"' in page
    page = client.post(f"/app/tickets/{ticket_id}/answer", data={
        "question": "What temperature does the display show?", "answer": "48 F", "kind": "reading"}).text
    assert 'value="48 F"' in page and "Refine diagnosis with 1 answer" in page
    with Session(engine) as s:
        assert s.get(Ticket, ticket_id).answers["What temperature does the display show?"]["answer"] == "48 F"
