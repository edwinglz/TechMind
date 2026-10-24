"""The committed demo history still contains every pattern the demo relies on."""

import csv

from app.config import settings
from scripts.generate_demo_history import check_patterns, generate, generate_assets


def test_committed_history_has_planned_patterns():
    with open(settings.demo_data_dir / "ticket_history.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert check_patterns(rows) == []


def _committed(name):
    with open(settings.demo_data_dir / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_generator_is_deterministic():
    """Regenerating must reproduce the committed files exactly (same seed, same rows)."""
    assets = generate_assets()
    assert assets == _committed("assets.csv")
    tickets = _committed("ticket_history.csv")
    assert [{k: str(r[k]) for k in tickets[0]} for r in generate(assets)] == tickets
