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
os.environ["AGENT_DB_PATH"] = str(_TMP / "test.db")
os.environ["AGENT_LOG_PATH"] = str(_TMP / "test.jsonl")
os.environ.setdefault("AGENT_MODE", "paper")
os.environ.setdefault("AGENT_BANKROLL", "50")
os.environ.setdefault("AGENT_PER_MARKET_CAP", "2")
os.environ.setdefault("AGENT_CATEGORIES", "geopolitics,world,politics")

import pytest  # noqa: E402

from agent.store import db  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _init_schema():
    db.init_db(Path(os.environ["AGENT_DB_PATH"]))
    yield


@pytest.fixture(autouse=True)
def _clean_breakers():
    """Reset breaker state between tests so they don't bleed into each other."""
    with db.connect() as conn:
        conn.execute("DELETE FROM breaker_state")
    yield


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    p = tmp_path / "fresh.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(p))
    import agent.config as cfg
    cfg.settings = cfg.Settings()
    db.init_db(p)
    yield p
