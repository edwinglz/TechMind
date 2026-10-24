"""Importer: the demo data validates and loads; bad files produce clear errors."""

from collections import Counter

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from app.config import settings
from app.db import init_db, make_engine
from app.importer.load import load_company
from app.importer.manuals import split_markdown
from app.importer.parse import parse_bundle, read_folder
from app.models import FixVariant, KnownIssue, ManualChunk, Ticket


@pytest.fixture(scope="module")
def demo_files():
    return read_folder(settings.demo_data_dir)


@pytest.fixture()
def db():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as session:
        yield session


def test_demo_data_is_valid(demo_files):
    bundle = parse_bundle(demo_files)
    assert bundle.ok, bundle.all_errors()
    counts = {name: report.rows for name, report in bundle.reports.items()}
    assert counts == {
        "profile.json": 1, "settings.csv": 1, "sites.csv": 8, "products.csv": 7, "assets.csv": 58,
        "parts.csv": 34, "known_issues.csv": 31, "ticket_history.csv": 125, "manuals": 7,
    }
    assert not any(r.warnings for r in bundle.reports.values())


def test_load_demo_company(demo_files, db):
    company = load_company(db, parse_bundle(demo_files))
    db.commit()
    assert company.name == "Kestrel Burger Co."
    assert company.trip_fee == 95.0
    assert db.exec(select(Ticket)).all().__len__() == 125

    # The carbonator issue has its documented fix plus the newer one found in history.
    issue = db.exec(select(KnownIssue).where(KnownIssue.ref == "KI-CI-03")).one()
    variants = db.exec(select(FixVariant).where(FixVariant.known_issue_id == issue.id)).all()
    assert sorted(v.source for v in variants) == ["history", "import"]
    stats = Counter()
    for t in db.exec(select(Ticket).where(Ticket.known_issue_id == issue.id)).all():
        stats[(t.fix_variant_id, t.resolved)] += 1
    original = next(v for v in variants if v.source == "import")
    newer = next(v for v in variants if v.source == "history")
    assert stats[(original.id, True)] == 5 and stats[(original.id, False)] == 3
    assert stats[(newer.id, True)] == 2

    # Self-fixed tickets are not attached to a technician fix variant.
    self_fixed = db.exec(select(Ticket).where(Ticket.resolved_by_reporter == True)).all()  # noqa: E712
    assert len(self_fixed) == 37
    assert all(t.fix_variant_id is None for t in self_fixed)


def test_manual_search_index(demo_files, db):
    load_company(db, parse_bundle(demo_files))
    db.commit()
    rows = db.execute(text(
        "SELECT section_title FROM manual_chunks_fts WHERE manual_chunks_fts MATCH 'flat AND carbonation' "
        "ORDER BY rank LIMIT 3")).all()
    assert rows and "No carbonation" in rows[0][0]
    assert db.exec(select(ManualChunk)).first() is not None
    # Porter stemming: "leaking" in a description matches the word "leak" in the query.
    hits = db.execute(text("SELECT count(*) FROM tickets_fts WHERE tickets_fts MATCH 'leak'")).scalar()
    assert hits > 0


def test_split_markdown_keeps_parent_heading():
    sections = split_markdown("# Title\nintro\n## Troubleshooting\n### Leaks\n| a | b |\n## Safety\nbe careful")
    assert [s.title for s in sections] == ["Introduction", "Troubleshooting > Leaks", "Safety"]


def _with(files, name, content):
    changed = dict(files)
    changed[name] = content.encode()
    return changed


def test_missing_required_file(demo_files):
    files = {k: v for k, v in demo_files.items() if k != "sites.csv"}
    bundle = parse_bundle(files)
    assert not bundle.ok
    assert "file is missing" in bundle.reports["sites.csv"].errors


def test_missing_column(demo_files):
    bundle = parse_bundle(_with(demo_files, "sites.csv", "site_id,name\nS01,One\n"))
    assert any("missing column(s): address, region" in e for e in bundle.reports["sites.csv"].errors)


def test_bad_reference_and_value_report_row_numbers(demo_files):
    assets = ("asset_id,model_id,site_id,serial,install_date,last_service_date\n"
              "A-1,CI-200,S01,x,2024-01-01,\n"
              "A-2,NOPE,S01,x,,\n"
              "A-3,CI-200,S01,x,yesterday,\n")
    bundle = parse_bundle(_with(demo_files, "assets.csv", assets))
    errors = bundle.reports["assets.csv"].errors
    assert any(e.startswith("row 3:") and "NOPE" in e for e in errors)
    assert any(e.startswith("row 4:") and "install_date" in e for e in errors)


def test_bad_yes_no(demo_files):
    original = demo_files["known_issues.csv"].decode()
    broken = original.replace(",15,y\n", ",15,maybe\n", 1)
    bundle = parse_bundle(_with(demo_files, "known_issues.csv", broken))
    assert any("must be y or n" in e for e in bundle.reports["known_issues.csv"].errors)


def test_profile_needs_labels(demo_files):
    bundle = parse_bundle(_with(demo_files, "profile.json", '{"industry": "x", "labels": {}}'))
    errors = bundle.reports["profile.json"].errors
    assert "'labels.site' is required" in errors
    assert "'self_fix_allowed' must be a list of strings" in errors
