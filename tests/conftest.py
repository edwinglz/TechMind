"""Test setup: point the app at a throwaway database before anything imports it."""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="techmind-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["AI_MODE"] = "mock"
os.environ["AS_OF_DATE"] = "2026-10-24"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DEMO_PASSWORD"] = "test-password"
