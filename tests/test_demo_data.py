"""The committed demo history still contains every pattern the demo relies on."""

import csv

from app.config import settings
from scripts.generate_demo_history import check_patterns, generate


def test_committed_history_has_planned_patterns():
    with open(settings.demo_data_dir / "ticket_history.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert check_patterns(rows) == []


def test_generator_is_deterministic():
    """Regenerating must reproduce the committed file exactly (same seed, same rows)."""
    rows, _ = generate()
    with open(settings.demo_data_dir / "ticket_history.csv", newline="", encoding="utf-8") as f:
        committed = list(csv.DictReader(f))
    assert [{k: str(v) for k, v in r.items()} for r in rows] == committed
