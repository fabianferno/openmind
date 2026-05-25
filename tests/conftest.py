"""pytest fixtures.

Env vars MUST be set before `agent.config` is imported anywhere, so we do it at module
load time (before any other imports below).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# ---- env setup (runs before any agent imports) ----
_TMP = Path(tempfile.mkdtemp(prefix="openclob-test-"))
os.environ["MONGO_DB_URL"] = "mongodb://localhost:27017"
os.environ["MONGO_DB_NAME"] = "openclob_test"
os.environ["AGENT_LOG_PATH"] = str(_TMP / "test.jsonl")
os.environ.setdefault("AGENT_MODE", "paper")
os.environ.setdefault("AGENT_BANKROLL", "50")
os.environ.setdefault("AGENT_PER_MARKET_CAP", "2")
os.environ.setdefault("AGENT_CATEGORIES", "geopolitics,world,politics")

import mongomock  # noqa: E402
import pytest  # noqa: E402

from agent.store import db  # noqa: E402


@pytest.fixture(autouse=True)
def _mongo(monkeypatch):
    """Give every test a fresh in-memory MongoDB via mongomock."""
    client = mongomock.MongoClient()
    monkeypatch.setattr(db, "_client", client)
    db.init_db()
    yield
    client.drop_database("openclob_test")


@pytest.fixture
def fresh_db(monkeypatch):
    """A clean DB for a single test (mongomock is already per-test isolated)."""
    client = mongomock.MongoClient()
    monkeypatch.setattr(db, "_client", client)
    db.init_db()
    yield
