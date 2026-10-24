"""Database engine, sessions, and the SQLite full-text search (FTS5) indexes.

FTS5 tables are SQLite "virtual tables" that SQLModel can't declare, so they are
created here with plain SQL. They hold a searchable copy of the text plus the
ids needed to find the original row.
"""

from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers the tables on SQLModel.metadata)
from app.config import settings

# porter = match word stems ("leaking" finds "leak"); unicode61 = sensible tokenizing.
FTS_TABLES = [
    """CREATE VIRTUAL TABLE IF NOT EXISTS manual_chunks_fts USING fts5(
        section_title, content,
        chunk_id UNINDEXED, company_id UNINDEXED, product_id UNINDEXED,
        tokenize = 'porter unicode61')""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS tickets_fts USING fts5(
        description,
        ticket_id UNINDEXED, company_id UNINDEXED, product_id UNINDEXED,
        tokenize = 'porter unicode61')""",
]


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    new_engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(new_engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")

    return new_engine


engine = make_engine(settings.database_url)


def init_db(target: Engine = engine) -> None:
    """Create all tables and FTS indexes if they don't exist yet."""
    SQLModel.metadata.create_all(target)
    with target.begin() as conn:
        for statement in FTS_TABLES:
            conn.execute(text(statement))


def get_session():
    """FastAPI dependency: one session per request."""
    with Session(engine) as session:
        yield session
