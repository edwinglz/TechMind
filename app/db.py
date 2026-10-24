"""Database engine, sessions, and the SQLite full-text search (FTS5) indexes.

FTS5 tables are SQLite "virtual tables" that SQLModel can't declare, so they are
created here with plain SQL. They hold a searchable copy of the text plus the
ids needed to find the original row.
"""

from pathlib import Path

from sqlalchemy import event, inspect, text
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


class OutdatedDatabaseError(RuntimeError):
    """The database file was created by an older version of the tables."""


def _missing_columns(target: Engine) -> list[str]:
    """Columns the code expects that an existing database file doesn't have."""
    inspector = inspect(target)
    missing = []
    for table in SQLModel.metadata.sorted_tables:
        if inspector.has_table(table.name):
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            missing += [f"{table.name}.{c.name}" for c in table.columns if c.name not in existing]
    return missing


def init_db(target: Engine = engine) -> None:
    """Create all tables and FTS indexes if they don't exist yet.

    `create_all` only adds missing tables; it never changes existing ones. There
    are no migrations in this project, so if a table gained columns since the
    database file was created, stop at startup with a clear message instead of
    failing later with "Internal Server Error" on whichever page touches it.
    """
    missing = _missing_columns(target)
    if missing:
        raise OutdatedDatabaseError(
            f"The database ({target.url}) was created by an older version of TechMind and is missing "
            f"{', '.join(missing)}. Stop the server, delete the database file (data/techmind.db by default), "
            "and start again; the demo company is re-seeded automatically."
        )
    SQLModel.metadata.create_all(target)
    with target.begin() as conn:
        for statement in FTS_TABLES:
            conn.execute(text(statement))


def get_session():
    """FastAPI dependency: one session per request."""
    with Session(engine) as session:
        yield session
