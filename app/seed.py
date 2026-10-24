"""Load the demo company from demo_data/ when the database is empty.

Runs on every startup but only does work the first time, so a fresh deploy
(or a deleted local database) always comes up with demo data ready.

It also creates the demo accounts. They all share DEMO_PASSWORD from .env;
if that is blank, a random password is generated and printed once in the log.
"""

import logging
import secrets

from sqlmodel import Session, select

from app.auth import hash_password
from app.config import settings
from app.db import engine
from app.importer.load import load_company
from app.importer.parse import parse_bundle, read_folder
from app.models import Company, User

log = logging.getLogger(__name__)

# (username, display name, role)
DEMO_USERS = [("manager", "Manager", "manager"), ("ana", "Ana", "technician"), ("luis", "Luis", "technician")]


def seed_if_empty() -> None:
    with Session(engine) as session:
        if session.exec(select(Company)).first():
            return
        bundle = parse_bundle(read_folder(settings.demo_data_dir))
        if not bundle.ok:
            raise RuntimeError("Demo data failed validation:\n" + "\n".join(bundle.all_errors()))
        company = load_company(session, bundle)

        password = settings.demo_password
        if not password:
            password = secrets.token_urlsafe(9)
            log.warning("DEMO_PASSWORD is not set; generated demo password: %s", password)
        password_hash = hash_password(password)  # same password, so hash once
        for username, name, role in DEMO_USERS:
            session.add(User(company_id=company.id, username=username, password_hash=password_hash,
                             name=name, role=role))

        session.commit()
        log.info("Seeded demo company %r with users %s", company.name, ", ".join(u[0] for u in DEMO_USERS))
