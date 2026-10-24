"""Load the demo company from demo_data/ when the database is empty.

Runs on every startup but only does work the first time, so a fresh deploy
(or a deleted local database) always comes up with demo data ready.
"""

import logging

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.importer.load import load_company
from app.importer.parse import parse_bundle, read_folder
from app.models import Company

log = logging.getLogger(__name__)


def seed_if_empty() -> None:
    with Session(engine) as session:
        if session.exec(select(Company)).first():
            return
        bundle = parse_bundle(read_folder(settings.demo_data_dir))
        if not bundle.ok:
            raise RuntimeError("Demo data failed validation:\n" + "\n".join(bundle.all_errors()))
        company = load_company(session, bundle)
        session.commit()
        log.info("Seeded demo company %r from %s", company.name, settings.demo_data_dir)
