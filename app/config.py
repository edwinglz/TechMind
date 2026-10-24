"""Application settings, read once at startup from environment variables.

Values come from the real environment first, then from a `.env` file in the
project root (see `.env.example` for every variable and what it does).
"""

import os
import secrets
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    ai_mode: str  # "mock" or "live"
    anthropic_api_key: str
    database_url: str
    upload_dir: Path
    as_of_date: date | None
    demo_data_dir: Path
    fixtures_dir: Path
    secret_key: str  # signs the login cookie
    demo_password: str  # blank = generate one when seeding


def _project_path(value: str) -> Path:
    """Resolve a relative path against the project root, not the current directory."""
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def _load() -> Settings:
    ai_mode = os.getenv("AI_MODE", "mock").strip().lower()
    if ai_mode not in ("mock", "live"):
        raise ValueError(f"AI_MODE must be 'mock' or 'live', got {ai_mode!r}")

    as_of_raw = os.getenv("AS_OF_DATE", "").strip()
    as_of_date = date.fromisoformat(as_of_raw) if as_of_raw else None

    default_db = (BASE_DIR / "data" / "techmind.db").as_posix()
    return Settings(
        ai_mode=ai_mode,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        database_url=os.getenv("DATABASE_URL", "").strip() or f"sqlite:///{default_db}",
        upload_dir=_project_path(os.getenv("UPLOAD_DIR", "").strip() or "uploads"),
        as_of_date=as_of_date,
        demo_data_dir=BASE_DIR / "demo_data",
        fixtures_dir=BASE_DIR / "fixtures",
        # Without a configured key, a random one still keeps cookies unforgeable;
        # it just logs everyone out whenever the server restarts.
        secret_key=os.getenv("SECRET_KEY", "").strip() or secrets.token_hex(32),
        demo_password=os.getenv("DEMO_PASSWORD", "").strip(),
    )


settings = _load()


def today() -> date:
    """The date that trend and repeat-failure math treats as "today".

    Normally the real date. Setting AS_OF_DATE pins it, so the demo data's
    planned patterns (which are relative to late October 2026) still show up
    if the demo runs later.
    """
    return settings.as_of_date or date.today()
