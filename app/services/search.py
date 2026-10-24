"""Keep the FTS5 full-text indexes in step with the tables they search.

The FTS tables (created in app/db.py) store a searchable copy of manual
sections and ticket descriptions. Whenever a chunk or ticket is created, it must
also be written here or keyword search won't find it.
"""

from sqlalchemy import text
from sqlmodel import Session

from app.models import ManualChunk, Ticket


def index_manual_chunk(session: Session, chunk: ManualChunk) -> None:
    session.execute(
        text("INSERT INTO manual_chunks_fts (section_title, content, chunk_id, company_id, product_id) "
             "VALUES (:title, :content, :id, :company_id, :product_id)"),
        {"title": chunk.section_title, "content": chunk.content, "id": chunk.id,
         "company_id": chunk.company_id, "product_id": chunk.product_id},
    )


def index_ticket(session: Session, ticket: Ticket) -> None:
    session.execute(
        text("INSERT INTO tickets_fts (description, ticket_id, company_id, product_id) "
             "VALUES (:description, :id, :company_id, :product_id)"),
        {"description": ticket.description, "id": ticket.id,
         "company_id": ticket.company_id, "product_id": ticket.product_id},
    )
