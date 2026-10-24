"""FastAPI application entry point.

Start locally with:  uvicorn app.main:app --reload
On startup it creates any missing tables and seeds the demo company if the
database is empty.

URL layout: "/" is the public product page, "/login" the login form, and
everything under "/app" is the product itself (login required).
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routes import dashboard, login, public
from app.seed import seed_if_empty

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("techmind")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    seed_if_empty()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    log.info("TechMind ready (AI_MODE=%s)", settings.ai_mode)
    yield


app = FastAPI(title="TechMind", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(public.router)
app.include_router(login.router)
app.include_router(dashboard.router)
