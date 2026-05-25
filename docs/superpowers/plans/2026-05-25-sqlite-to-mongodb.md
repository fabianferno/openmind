# SQLite → MongoDB Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SQLite with MongoDB (Atlas, db `openmind`) as openclob's persistence layer, migrate all existing data losslessly, verify, then remove SQLite.

**Architecture:** Keep `db.connect()` as a context manager but yield a `pymongo` `Database` instead of a `sqlite3.Connection`. All 30 DAO functions keep their signatures and return shapes, so the 71 call sites are untouched. Integer IDs are preserved via a `counters` collection and stored as `_id`; on read, `_id` is mapped back to the original key name (`id`/`day`/`name`/`pattern`/`decision_id`). JSON-text columns are stored verbatim as strings to keep API payloads and on-chain trace hashes byte-identical.

**Tech Stack:** Python, pymongo, mongomock (tests), pydantic-settings, click, FastAPI.

---

## File Structure

- `pyproject.toml` — add `pymongo` (runtime), `mongomock` (dev).
- `agent/config.py` — add `mongo_db_url`, `mongo_db_name`; later remove `agent_db_path`.
- `.env.example` — add `MONGO_DB_URL`, `MONGO_DB_NAME`; later remove `AGENT_DB_PATH`.
- `agent/store/db.py` — **rewritten** as a pymongo DAO. Same public functions + new ones for ex-raw-SQL sites.
- `agent/store/schema.sql` — **deleted** in the deletion phase.
- `tests/conftest.py` — point `connect()` at mongomock.
- `tests/test_db_roundtrips.py` — replace raw SELECT/INSERT with DAO calls.
- `agent/monitor/positions.py`, `agent/__main__.py`, `agent/api/server.py`, `agent/backtest/harness.py`, `agent/strategy/calibration.py` — replace embedded raw SQL with new DAO calls.
- `tools/migrate_sqlite_to_mongo.py` — **new** one-time migration + verification script.

---

## Task 1: Add deps + Mongo config

**Files:**
- Modify: `pyproject.toml`
- Modify: `agent/config.py:84-88`
- Modify: `.env.example`

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, add `"pymongo>=4.6"` to the runtime `dependencies` list, and `"mongomock>=4.1"` to the `[project.optional-dependencies]` `dev` list. Then:

```bash
source .venv/bin/activate && pip install -e ".[dev]"
```

- [ ] **Step 2: Add config fields**

In `agent/config.py`, under the `# ---- storage / obs ----` block (currently line 84), add the two Mongo fields **above** `agent_db_path` (keep `agent_db_path` for now — removed in Task 9):

```python
    # ---- storage / obs ----
    mongo_db_url: str = ""
    mongo_db_name: str = "openmind"
    agent_db_path: Path = Path("data/agent.db")
```

- [ ] **Step 3: Update .env.example**

In `.env.example`, near the existing `AGENT_DB_PATH=data/agent.db` line, add:

```
MONGO_DB_URL=mongodb+srv://user:pass@cluster/...
MONGO_DB_NAME=openmind
```

- [ ] **Step 4: Verify config loads**

Run: `python -c "from agent.config import settings; print(settings.mongo_db_name, bool(settings.mongo_db_url))"`
Expected: `openmind True` (the `.env` already has `MONGO_DB_URL`).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml agent/config.py .env.example
git commit -m "Add pymongo/mongomock deps and Mongo config settings"
```

---

## Task 2: Point tests at mongomock

This must come before rewriting `db.py` so the rewritten DAO can be tested offline. `conftest.py` monkeypatches `db`'s cached client to a mongomock client.

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Rewrite conftest.py**

Replace the entire contents of `tests/conftest.py` with:

```python
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
```

Note: `_clean_breakers` is gone — mongomock gives each test a fresh DB, so breakers can't bleed. `fresh_db` no longer yields a path; the two tests that referenced its value don't use the value (they only need isolation).

- [ ] **Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "Switch test fixtures to mongomock"
```

(The suite will not pass yet — `db.py` is still SQLite. Next task fixes that.)

---

## Task 3: Rewrite db.py as a pymongo DAO

**Files:**
- Rewrite: `agent/store/db.py`
- Test: `tests/test_db_roundtrips.py`

- [ ] **Step 1: Update test_db_roundtrips.py (failing tests first)**

Replace the three raw-SQL spots so the tests use the DAO. Replace the whole file with:

```python
from agent.store import db


def test_market_upsert_and_get():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {
            "venue": "test",
            "external_id": "m1",
            "question": "Q?",
            "category": "geopolitics",
            "end_date": "2030-01-01T00:00:00+00:00",
            "last_price_yes": 0.4,
            "volume_24h": 1234.0,
        })
        got = db.get_market(conn, mid)
    assert got and got["question"] == "Q?"
    assert got["id"] == mid
    assert got["volume_24h"] == 1234.0


def test_decision_roundtrip():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {"venue": "t", "external_id": "m2", "question": "Q"})
        did = db.record_decision(conn, {
            "market_id": mid, "kind": "entry", "as_of": "2024-01-01T00:00:00+00:00",
            "prompt": "p", "search_used": [{"url": "u"}],
            "model_id": "x", "response_raw": "{}", "response_json": {"a": 1},
            "p_yes": 0.55, "confidence": 0.6, "action": "enter_yes",
            "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001,
        })
        row = db.get_decision(conn, did)
    assert isinstance(did, int)
    assert row["id"] == did
    assert row["p_yes"] == 0.55
    assert row["action"] == "enter_yes"
    assert row["cost_usd"] == 0.001


def test_decision_ids_are_sequential():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {"venue": "t", "external_id": "seq", "question": "Q"})
        a = db.record_decision(conn, {
            "market_id": mid, "kind": "entry", "as_of": "x", "prompt": "p",
            "model_id": "x", "response_raw": "{}",
        })
        b = db.record_decision(conn, {
            "market_id": mid, "kind": "entry", "as_of": "x", "prompt": "p",
            "model_id": "x", "response_raw": "{}",
        })
    assert b == a + 1


def test_position_open_close():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {"venue": "t", "external_id": "m3", "question": "Q"})
        pid = db.open_position(conn, {
            "market_id": mid, "venue": "t", "side": "YES",
            "shares": 10.0, "entry_price": 0.4, "notional_in": 4.0,
        })
        db.close_position(
            conn, pid, exit_price=0.55, notional_out=5.5,
            exit_decision_id=None, venue_exit_order=None,
            p_yes_at_exit=0.55, fees=0.0,
        )
        rows = db.all_positions(conn)
    row = next(r for r in rows if r["id"] == pid)
    assert row["status"] == "closed"
    assert abs(row["pnl"] - 1.5) < 1e-6


def test_llm_usage_accumulates():
    with db.connect() as conn:
        db.add_llm_usage(conn, 100, 200, 0.001)
        db.add_llm_usage(conn, 50, 60, 0.0005)
        spent = db.llm_cost_today(conn)
    assert abs(spent - 0.0015) < 1e-9


def test_blocklist_substring_match():
    with db.connect() as conn:
        db.add_blocklist(conn, "forbidden", "test")
        assert db.in_blocklist(conn, "this is a FORBIDDEN topic")
        assert not db.in_blocklist(conn, "this is fine")


def test_snapshot_at_or_before():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {"venue": "t", "external_id": "snap", "question": "Q"})
        db.insert_snapshot(conn, {"market_id": mid, "as_of": "2024-01-01T00:00:00+00:00",
                                   "price_yes": 0.3})
        db.insert_snapshot(conn, {"market_id": mid, "as_of": "2024-02-01T00:00:00+00:00",
                                   "price_yes": 0.4})
        # duplicate (market_id, as_of) is ignored
        db.insert_snapshot(conn, {"market_id": mid, "as_of": "2024-01-01T00:00:00+00:00",
                                   "price_yes": 0.99})
        snap = db.snapshot_at_or_before(conn, mid, "2024-01-15T00:00:00+00:00")
    assert snap is not None
    assert abs(snap["price_yes"] - 0.3) < 1e-9


def test_graph_roundtrip():
    with db.connect() as conn:
        mid = db.upsert_market(conn, {"venue": "t", "external_id": "g", "question": "Q"})
        did = db.record_decision(conn, {
            "market_id": mid, "kind": "entry", "as_of": "x", "prompt": "p",
            "model_id": "x", "response_raw": "{}",
        })
        db.save_graph(
            conn, decision_id=did, market_id=mid, as_of="x",
            ontology={"entity_types": ["A"]}, stats={"node_count": 1},
            nodes=[{"id": "n1", "label": "N1", "type": "A"}],
            edges=[{"source": "n1", "target": "n1", "type": "REL"}],
        )
        g = db.get_graph(conn, did)
    assert g["ontology"] == {"entity_types": ["A"]}
    assert g["stats"] == {"node_count": 1}
    assert g["nodes"][0]["label"] == "N1"
    assert g["edges"][0]["type"] == "REL"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db_roundtrips.py -q`
Expected: errors/failures (db.py still SQLite; `add_blocklist`/`get_graph` shape differs / mongomock client unused).

- [ ] **Step 3: Rewrite db.py**

Replace the **entire** contents of `agent/store/db.py` with:

```python
"""MongoDB DAO. Thin wrapper around pymongo with typed dict rows.

Public functions keep their SQLite-era signatures and return shapes. Integer
record ids are issued by a `counters` collection and stored as `_id`; reads map
`_id` back to the original key name. JSON-text columns are stored verbatim as
strings (as SQLite held them) to keep API payloads and on-chain trace hashes
byte-identical.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from pymongo import DESCENDING, MongoClient, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from agent.config import settings

_client: MongoClient | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.mongo_db_url)
    return _client


@contextmanager
def connect() -> Iterator[Database]:
    """Yield the shared `openmind` database handle. Client is pooled, not closed."""
    yield get_client()[settings.mongo_db_name]


def init_db() -> None:
    """Create indexes mirroring the old SQLite schema. Idempotent."""
    d = get_client()[settings.mongo_db_name]
    d["markets"].create_index([("venue", 1), ("external_id", 1)])
    d["markets"].create_index([("resolved", 1), ("end_date", 1)])
    d["markets"].create_index([("category", 1)])
    d["decisions"].create_index([("market_id", 1), ("kind", 1), ("created_at", 1)])
    d["positions"].create_index([("status", 1)])
    d["positions"].create_index([("market_id", 1)])
    d["orders"].create_index([("status", 1), ("expires_at", 1)])
    d["market_snapshots"].create_index([("market_id", 1), ("as_of", 1)], unique=True)
    d["metrics"].create_index([("as_of", 1), ("category", 1)], unique=True)
    d["graph_nodes"].create_index([("decision_id", 1)])
    d["graph_edges"].create_index([("decision_id", 1)])
    d["onchain_anchors"].create_index([("decision_id", 1)])


def next_id(conn: Database, name: str) -> int:
    """Issue the next sequential integer id for `name` (autoincrement emulation)."""
    doc = conn["counters"].find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


def _out(doc: dict[str, Any] | None, id_field: str = "id") -> dict[str, Any] | None:
    """Map a stored doc to the SQLite-era row shape: `_id` -> `id_field`."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc[id_field] = doc.pop("_id")
    return doc


# ---------- markets ----------

def upsert_market(conn: Database, m: dict[str, Any]) -> str:
    """Upsert market doc. `m` must include venue, external_id, question."""
    market_id = m.get("id") or f"{m['venue']}:{m['external_id']}"
    now = _now()
    conn["markets"].update_one(
        {"_id": market_id},
        {
            "$set": {
                "question": m["question"],
                "category": m.get("category"),
                "resolution_source": m.get("resolution_source"),
                "resolution_rules": m.get("resolution_rules"),
                "yes_token_id": m.get("yes_token_id"),
                "no_token_id": m.get("no_token_id"),
                "end_date": m.get("end_date"),
                "closed_time": m.get("closed_time"),
                "resolved": 1 if m.get("resolved") else 0,
                "resolution_value": m.get("resolution_value"),
                "last_price_yes": m.get("last_price_yes"),
                "volume_24h": m.get("volume_24h"),
                "book_depth_5c": m.get("book_depth_5c"),
                "updated_at": now,
                "raw": json.dumps(m.get("raw")) if m.get("raw") else None,
            },
            "$setOnInsert": {
                "venue": m["venue"],
                "external_id": m["external_id"],
                "seen_at": now,
            },
        },
        upsert=True,
    )
    return market_id


def get_market(conn: Database, market_id: str) -> dict[str, Any] | None:
    return _out(conn["markets"].find_one({"_id": market_id}))


def list_resolved_markets(
    conn: Database, *, category: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    q: dict[str, Any] = {"resolved": 1, "resolution_value": {"$ne": None}}
    if category:
        q["category"] = category
    cur = conn["markets"].find(q).sort("end_date", DESCENDING)
    if limit:
        cur = cur.limit(limit)
    return [_out(r) for r in cur]


def list_open_markets(conn: Database, limit: int) -> list[dict[str, Any]]:
    cur = conn["markets"].find({"resolved": 0}).sort("volume_24h", DESCENDING).limit(limit)
    return [_out(r) for r in cur]


def list_tradeable_markets(conn: Database, limit: int) -> list[dict[str, Any]]:
    cur = (
        conn["markets"]
        .find({"resolved": 0, "last_price_yes": {"$gte": 0.05, "$lte": 0.95}})
        .sort("volume_24h", DESCENDING)
        .limit(limit)
    )
    return [_out(r) for r in cur]


# ---------- decisions ----------

def record_decision(conn: Database, d: dict[str, Any]) -> int:
    did = next_id(conn, "decisions")
    conn["decisions"].insert_one({
        "_id": did,
        "market_id": d["market_id"],
        "kind": d["kind"],
        "as_of": d["as_of"],
        "prompt": d["prompt"],
        "search_used": json.dumps(d["search_used"]) if d.get("search_used") is not None else None,
        "model_id": d["model_id"],
        "response_raw": d["response_raw"],
        "response_json": json.dumps(d["response_json"]) if d.get("response_json") is not None else None,
        "p_yes": d.get("p_yes"),
        "confidence": d.get("confidence"),
        "action": d.get("action"),
        "input_tokens": d.get("input_tokens", 0),
        "output_tokens": d.get("output_tokens", 0),
        "cost_usd": d.get("cost_usd", 0.0),
        "created_at": _now(),
    })
    return did


def get_decision(conn: Database, decision_id: int) -> dict[str, Any] | None:
    return _out(conn["decisions"].find_one({"_id": decision_id}))


def recent_decisions(
    conn: Database, *, kind: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    q = {"kind": kind} if kind else {}
    cur = conn["decisions"].find(q).sort("_id", DESCENDING).limit(limit)
    return [_out(r) for r in cur]


def latest_prior_p_yes(conn: Database, market_id: str) -> float | None:
    row = conn["decisions"].find_one(
        {"market_id": market_id, "p_yes": {"$ne": None}}, sort=[("_id", DESCENDING)]
    )
    return float(row["p_yes"]) if row else None


# ---------- positions ----------

def open_position(conn: Database, p: dict[str, Any]) -> int:
    pid = next_id(conn, "positions")
    conn["positions"].insert_one({
        "_id": pid,
        "market_id": p["market_id"],
        "venue": p["venue"],
        "side": p["side"],
        "shares": p["shares"],
        "entry_price": p["entry_price"],
        "exit_price": None,
        "notional_in": p["notional_in"],
        "notional_out": None,
        "pnl": None,
        "fees": 0.0,
        "status": "open",
        "entry_decision_id": p.get("entry_decision_id"),
        "exit_decision_id": None,
        "venue_entry_order": p.get("venue_entry_order"),
        "venue_exit_order": None,
        "p_yes_at_entry": p.get("p_yes_at_entry"),
        "p_yes_at_exit": None,
        "opened_at": _now(),
        "closed_at": None,
    })
    return pid


def close_position(
    conn: Database,
    pos_id: int,
    *,
    exit_price: float,
    notional_out: float,
    exit_decision_id: int | None,
    venue_exit_order: str | None,
    p_yes_at_exit: float | None,
    fees: float = 0.0,
) -> None:
    pos = conn["positions"].find_one({"_id": pos_id})
    if pos is None:
        return
    new_fees = float(pos.get("fees") or 0.0) + fees
    pnl = notional_out - float(pos["notional_in"]) - fees
    conn["positions"].update_one(
        {"_id": pos_id},
        {"$set": {
            "exit_price": exit_price,
            "notional_out": notional_out,
            "pnl": pnl,
            "fees": new_fees,
            "status": "closed",
            "exit_decision_id": exit_decision_id,
            "venue_exit_order": venue_exit_order,
            "p_yes_at_exit": p_yes_at_exit,
            "closed_at": _now(),
        }},
    )


def open_positions(conn: Database) -> list[dict[str, Any]]:
    cur = conn["positions"].find({"status": "open"}).sort("opened_at", 1)
    return [_out(r) for r in cur]


def all_positions(conn: Database, limit: int = 200) -> list[dict[str, Any]]:
    cur = conn["positions"].find().sort("_id", DESCENDING).limit(limit)
    return [_out(r) for r in cur]


def positions_with_market(conn: Database, limit: int = 200) -> list[dict[str, Any]]:
    """Positions newest-first, each enriched with its market `question` and `venue`."""
    rows = [_out(r) for r in conn["positions"].find().sort("_id", DESCENDING).limit(limit)]
    ids = list({r["market_id"] for r in rows})
    markets = {m["_id"]: m for m in conn["markets"].find({"_id": {"$in": ids}})}
    for r in rows:
        m = markets.get(r["market_id"])
        r["question"] = m["question"] if m else None
        r["venue"] = m["venue"] if m else r.get("venue")  # market venue overrides (matches old LEFT JOIN)
    return rows


def positions_today_pnl(conn: Database) -> float:
    today = datetime.now(UTC).date().isoformat()
    total = 0.0
    for r in conn["positions"].find({"status": "closed", "closed_at": {"$regex": f"^{today}"}}):
        total += float(r.get("pnl") or 0.0)
    return total


def latest_open_position_for_market(conn: Database, market_id: str) -> dict[str, Any] | None:
    row = conn["positions"].find_one(
        {"market_id": market_id, "status": "open"}, sort=[("_id", DESCENDING)]
    )
    return _out(row)


def simulated_closed_pnl(conn: Database) -> list[dict[str, Any]]:
    cur = conn["positions"].find({"venue": "simulated", "status": "closed"})
    return [{"pnl": r.get("pnl"), "notional_in": r.get("notional_in")} for r in cur]


# ---------- orders ----------

def record_order(conn: Database, o: dict[str, Any]) -> int:
    oid = next_id(conn, "orders")
    conn["orders"].insert_one({
        "_id": oid,
        "market_id": o["market_id"],
        "venue": o["venue"],
        "venue_order_id": o.get("venue_order_id"),
        "side": o["side"],
        "order_type": o["order_type"],
        "limit_price": o["limit_price"],
        "requested_size": o["requested_size"],
        "filled_size": 0.0,
        "status": o.get("status", "open"),
        "decision_id": o.get("decision_id"),
        "created_at": _now(),
        "expires_at": o["expires_at"],
        "closed_at": None,
    })
    return oid


def open_orders(conn: Database) -> list[dict[str, Any]]:
    cur = conn["orders"].find({"status": {"$in": ["open", "partial"]}}).sort("created_at", 1)
    return [_out(r) for r in cur]


def update_order(conn: Database, order_id: int, **fields: Any) -> None:
    if not fields:
        return
    conn["orders"].update_one({"_id": order_id}, {"$set": fields})


# ---------- llm budget ----------

def add_llm_usage(conn: Database, input_tokens: int, output_tokens: int, cost: float) -> None:
    day = datetime.now(UTC).date().isoformat()
    conn["llm_usage"].update_one(
        {"_id": day},
        {"$inc": {"input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": cost}},
        upsert=True,
    )


def llm_cost_today(conn: Database) -> float:
    day = datetime.now(UTC).date().isoformat()
    row = conn["llm_usage"].find_one({"_id": day})
    return float(row["cost_usd"]) if row else 0.0


# ---------- breakers ----------

def set_breaker(conn: Database, name: str, *, tripped: bool, reason: str | None = None,
                expires_at: str | None = None) -> None:
    conn["breaker_state"].update_one(
        {"_id": name},
        {"$set": {
            "tripped": 1 if tripped else 0,
            "tripped_at": _now() if tripped else None,
            "expires_at": expires_at,
            "reason": reason,
        }},
        upsert=True,
    )


def breaker_status(conn: Database, name: str) -> dict[str, Any] | None:
    return _out(conn["breaker_state"].find_one({"_id": name}), "name")


def all_breakers(conn: Database) -> list[dict[str, Any]]:
    return [_out(r, "name") for r in conn["breaker_state"].find()]


def clear_breakers(conn: Database) -> None:
    conn["breaker_state"].delete_many({})


# ---------- snapshots ----------

def insert_snapshot(conn: Database, s: dict[str, Any]) -> None:
    """INSERT-OR-IGNORE on (market_id, as_of)."""
    try:
        conn["market_snapshots"].insert_one({
            "_id": next_id(conn, "market_snapshots"),
            "market_id": s["market_id"],
            "as_of": s["as_of"],
            "price_yes": s["price_yes"],
            "book_depth_5c": s.get("book_depth_5c"),
            "volume_24h": s.get("volume_24h"),
            "raw": json.dumps(s.get("raw")) if s.get("raw") else None,
        })
    except DuplicateKeyError:
        pass


def snapshot_at_or_before(
    conn: Database, market_id: str, as_of: str
) -> dict[str, Any] | None:
    row = conn["market_snapshots"].find_one(
        {"market_id": market_id, "as_of": {"$lte": as_of}}, sort=[("as_of", DESCENDING)]
    )
    return _out(row)


# ---------- metrics ----------

def upsert_metrics(conn: Database, m: dict[str, Any]) -> None:
    conn["metrics"].update_one(
        {"as_of": m["as_of"], "category": m["category"]},
        {
            "$set": {
                "n_resolved": m["n_resolved"],
                "brier": m.get("brier"),
                "ece": m.get("ece"),
                "realized_pnl": m.get("realized_pnl", 0.0),
                "realized_roi": m.get("realized_roi"),
                "calibration_mul": m.get("calibration_mul", 0.5),
            },
            "$setOnInsert": {"_id": next_id(conn, "metrics")},
        },
        upsert=True,
    )


def _latest_metrics_rows(conn: Database) -> list[dict[str, Any]]:
    """Latest metrics row per category (max as_of), like the SQL correlated subquery."""
    by_cat: dict[str, dict[str, Any]] = {}
    for r in conn["metrics"].find():
        cat = r["category"]
        if cat not in by_cat or r["as_of"] > by_cat[cat]["as_of"]:
            by_cat[cat] = r
    return list(by_cat.values())


def latest_calibration_multipliers(conn: Database) -> dict[str, float]:
    return {r["category"]: float(r["calibration_mul"]) for r in _latest_metrics_rows(conn)}


def latest_metrics(conn: Database) -> list[dict[str, Any]]:
    rows = sorted(_latest_metrics_rows(conn), key=lambda r: r["category"])
    return [_out(r) for r in rows]


# ---------- blocklist ----------

def add_blocklist(conn: Database, pattern: str, reason: str = "") -> None:
    conn["blocklist"].update_one(
        {"_id": pattern},
        {"$set": {"reason": reason, "added_at": _now()}},
        upsert=True,
    )


def in_blocklist(conn: Database, question: str) -> bool:
    q = question.lower()
    return any(r["_id"].lower() in q for r in conn["blocklist"].find())


# ---------- graphrag ----------

def save_graph(
    conn: Database,
    *,
    decision_id: int,
    market_id: str,
    as_of: str,
    ontology: dict[str, Any],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    stats: dict[str, Any],
) -> None:
    """Persist an ontology + extracted graph for one entry decision (idempotent)."""
    now = _now()
    conn["graph_nodes"].delete_many({"decision_id": decision_id})
    conn["graph_edges"].delete_many({"decision_id": decision_id})
    conn["graph_runs"].update_one(
        {"_id": decision_id},
        {"$set": {
            "market_id": market_id,
            "as_of": as_of,
            "ontology_json": json.dumps(ontology),
            "stats_json": json.dumps(stats),
            "created_at": now,
        }},
        upsert=True,
    )
    for n in nodes:
        conn["graph_nodes"].insert_one({
            "_id": next_id(conn, "graph_nodes"),
            "decision_id": decision_id, "market_id": market_id,
            "node_key": n["id"], "label": n["label"], "type": n["type"],
            "summary": n.get("summary"), "source_url": n.get("source_url"),
            "published_date": n.get("published_date"), "degree": int(n.get("degree", 0)),
            "created_at": now,
        })
    for e in edges:
        conn["graph_edges"].insert_one({
            "_id": next_id(conn, "graph_edges"),
            "decision_id": decision_id, "market_id": market_id,
            "source_key": e["source"], "target_key": e["target"], "type": e["type"],
            "rationale": e.get("rationale"), "source_url": e.get("source_url"),
            "published_date": e.get("published_date"), "created_at": now,
        })


def get_graph(conn: Database, decision_id: int) -> dict[str, Any] | None:
    run = conn["graph_runs"].find_one({"_id": decision_id})
    if not run:
        return None
    nodes = [_out(r) for r in conn["graph_nodes"].find({"decision_id": decision_id}).sort("_id", 1)]
    edges = [_out(r) for r in conn["graph_edges"].find({"decision_id": decision_id}).sort("_id", 1)]
    return {
        "decision_id": decision_id,
        "ontology": json.loads(run["ontology_json"]),
        "stats": json.loads(run["stats_json"]),
        "nodes": nodes,
        "edges": edges,
        "as_of": run["as_of"],
    }


# ---------- reasoning-trace blobs ----------

def save_trace_blob(
    conn: Database,
    *,
    decision_id: int,
    market_id: str,
    trace_hash: str,
    canonical_json: str,
) -> None:
    conn["trace_blobs"].update_one(
        {"_id": decision_id},
        {"$set": {
            "market_id": market_id,
            "trace_hash": trace_hash,
            "canonical_json": canonical_json,
            "created_at": _now(),
        }},
        upsert=True,
    )


def get_trace_blob(conn: Database, decision_id: int) -> dict[str, Any] | None:
    return _out(conn["trace_blobs"].find_one({"_id": decision_id}), "decision_id")


# ---------- on-chain anchors ----------

def record_anchor(conn: Database, a: dict[str, Any]) -> int:
    aid = next_id(conn, "onchain_anchors")
    conn["onchain_anchors"].insert_one({
        "_id": aid,
        "decision_id": a.get("decision_id"),
        "market_id": a.get("market_id"),
        "kind": a["kind"],
        "trace_hash": a.get("trace_hash"),
        "tx_hash": a["tx_hash"],
        "explorer_url": a.get("explorer_url"),
        "usdc_amount": a.get("usdc_amount"),
        "to_address": a.get("to_address"),
        "network": a.get("network", "arc-testnet"),
        "mocked": 1 if a.get("mocked") else 0,
        "created_at": _now(),
    })
    return aid


def anchors_for_decision(conn: Database, decision_id: int) -> list[dict[str, Any]]:
    cur = conn["onchain_anchors"].find({"decision_id": decision_id}).sort("_id", 1)
    return [_out(r) for r in cur]


def recent_anchors(conn: Database, limit: int = 50) -> list[dict[str, Any]]:
    cur = conn["onchain_anchors"].find().sort("_id", DESCENDING).limit(limit)
    return [_out(r) for r in cur]
```

- [ ] **Step 4: Run roundtrip tests to verify they pass**

Run: `pytest tests/test_db_roundtrips.py -q`
Expected: all PASS.

- [ ] **Step 5: Run full suite (call sites still use old DAO functions — should pass except raw-SQL sites)**

Run: `pytest -q`
Expected: failures only in tests that exercise the not-yet-rewritten raw-SQL call sites (Task 4 fixes those). Note which fail.

- [ ] **Step 6: Commit**

```bash
git add agent/store/db.py tests/test_db_roundtrips.py
git commit -m "Rewrite store DAO on pymongo; preserve signatures and return shapes"
```

---

## Task 4: Rewrite the raw-SQL call sites

Each site swaps an embedded `conn.execute(...)` for a new DAO function from Task 3.

**Files:**
- Modify: `agent/monitor/positions.py:16-23`
- Modify: `agent/__main__.py:163-172`
- Modify: `agent/api/server.py` (3 spots)
- Modify: `agent/backtest/harness.py` (2 spots)
- Modify: `agent/strategy/calibration.py` (2 spots in `recompute()`)
- Modify: `tools/traction_run.py:27-37`
- Modify: `tools/seed_demo.py:21-32`

- [ ] **Step 1: positions.py**

Replace `_latest_prior_p_yes` body:

```python
def _latest_prior_p_yes(market_id: str) -> float | None:
    with db.connect() as conn:
        return db.latest_prior_p_yes(conn, market_id)
```

- [ ] **Step 2: __main__.py block command**

Replace the `with db.connect()` block in `block_cmd`:

```python
    from agent.store import db
    with db.connect() as conn:
        db.add_blocklist(conn, pattern, reason)
    click.echo(f"blocked: {pattern!r}")
```

(The `from datetime import ...` import inside the function is now unused — remove that line.)

- [ ] **Step 3: api/server.py `/api/markets`**

Replace the `with db.connect()` block (lines 83-93) so `rows` come from the DAO:

```python
    with db.connect() as conn:
        rows = db.list_open_markets(conn, limit)
    out = []
    for r in rows:
        d = dict(r)
        d["market_url"] = venue_market_url(d)
        d.pop("raw", None)
        d["seeded"] = any(s.startswith(d["id"].replace(":", "_")) for s in seeded)
        out.append(d)
    return {"markets": out, "seeds": list(seeded)}
```

- [ ] **Step 4: api/server.py `_pick_open_markets`**

```python
def _pick_open_markets(n: int) -> list[dict[str, Any]]:
    with db.connect() as conn:
        return db.list_tradeable_markets(conn, n)
```

- [ ] **Step 5: api/server.py `/api/portfolio`**

Replace the raw SELECT block (lines 286-296) so `positions` come from the DAO:

```python
    with db.connect() as conn:
        positions = db.positions_with_market(conn, 200)
        open_pos = [p for p in positions if p["status"] == "open"]
```

(Keep the remaining body of the function unchanged.)

- [ ] **Step 6: backtest/harness.py — latest open position**

Replace lines 121-128:

```python
            # close at resolution
            with db.connect() as conn:
                pos_dict = db.latest_open_position_for_market(conn, m["id"])
            if pos_dict:
                executor.close_position(
                    position=pos_dict, market=m, exit_decision_id=None, size_fraction=1.0,
                )
```

- [ ] **Step 7: backtest/harness.py — tally pnl**

Replace lines 137-143:

```python
    # tally pnl
    with db.connect() as conn:
        rows = db.simulated_closed_pnl(conn)
    for r in rows:
        pnl_total += float(r["pnl"] or 0.0)
        notional_total += float(r["notional_in"] or 0.0)
```

- [ ] **Step 8: strategy/calibration.py — replace the two raw queries**

The two SELECTs in `recompute()` join `decisions`/`positions` with `markets`. Replace them with Python that uses the DAO. Replace lines 81-109 (`rows = conn.execute(...)` through the `pnl_by_cat = {...}` line) with:

```python
        # Score every entry decision against the eventual market resolution.
        per_cat: dict[str, list[tuple[float, float]]] = {}
        all_preds: list[tuple[float, float]] = []
        for d in conn["decisions"].find({"kind": "entry", "p_yes": {"$ne": None}}):
            m = conn["markets"].find_one({"_id": d["market_id"]})
            if not m or m.get("resolved") != 1 or m.get("resolution_value") is None:
                continue
            cat = (m.get("category") or "uncategorised").lower()
            pair = (float(d["p_yes"]), float(m["resolution_value"]))
            per_cat.setdefault(cat, []).append(pair)
            all_preds.append(pair)

        pnl_by_cat: dict[str, tuple[float, float]] = {}
        for p in conn["positions"].find({"status": "closed"}):
            m = conn["markets"].find_one({"_id": p["market_id"]})
            cat = ((m.get("category") if m else None) or "uncategorised").lower()
            cur_pnl, cur_not = pnl_by_cat.get(cat, (0.0, 0.0))
            pnl_by_cat[cat] = (
                cur_pnl + float(p.get("pnl") or 0.0),
                cur_not + float(p.get("notional_in") or 0.0),
            )
```

This keeps `per_cat`, `all_preds`, and `pnl_by_cat` with identical shapes to the SQL version, so the rest of `recompute()` is unchanged.

- [ ] **Step 9: tools/traction_run.py — `gather()`**

Replace the `with db.connect()` block (lines 27-37) so `rows` come from the DAO:

```python
    with db.connect() as conn:
        return db.list_tradeable_markets(conn, n)
```

- [ ] **Step 10: tools/seed_demo.py — `pick_markets()`**

Replace the `with db.connect()` block (lines 22-32):

```python
    with db.connect() as conn:
        return db.list_tradeable_markets(conn, limit)
```

- [ ] **Step 11: Run full suite**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 12: Commit**

```bash
git add agent/monitor/positions.py agent/__main__.py agent/api/server.py agent/backtest/harness.py agent/strategy/calibration.py tools/traction_run.py tools/seed_demo.py
git commit -m "Move embedded raw SQL into the Mongo DAO"
```

---

## Task 5: Migration + verification script

**Files:**
- Create: `tools/migrate_sqlite_to_mongo.py`

- [ ] **Step 1: Write the script**

Create `tools/migrate_sqlite_to_mongo.py`:

```python
"""One-time migration: SQLite (data/agent.db) -> MongoDB (openmind).

Idempotent. Copies every row verbatim (PK column -> _id), seeds counters to
max(_id) for autoincrement tables, then verifies counts + a content spot-check.
Exits non-zero on any mismatch so the caller knows NOT to delete SQLite.

Usage:
    python tools/migrate_sqlite_to_mongo.py            # migrate + verify
    python tools/migrate_sqlite_to_mongo.py --verify   # verify only
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys

from agent.config import settings
from agent.store import db

# table -> primary-key column that becomes Mongo `_id`
TABLES = {
    "markets": "id",
    "decisions": "id",
    "positions": "id",
    "orders": "id",
    "metrics": "id",
    "llm_usage": "day",
    "breaker_state": "name",
    "market_snapshots": "id",
    "blocklist": "pattern",
    "graph_runs": "decision_id",
    "graph_nodes": "id",
    "graph_edges": "id",
    "trace_blobs": "decision_id",
    "onchain_anchors": "id",
}
# autoincrement tables whose counter must continue from max(_id)
INT_ID = {
    "decisions", "positions", "orders", "metrics",
    "market_snapshots", "graph_nodes", "graph_edges", "onchain_anchors",
}
SAMPLE = 25  # rows per table for the content spot-check


def _rows(sq: sqlite3.Connection, table: str) -> list[dict]:
    sq.row_factory = sqlite3.Row
    return [dict(r) for r in sq.execute(f"SELECT * FROM {table}")]


def _to_doc(row: dict, pk: str) -> dict:
    doc = dict(row)
    doc["_id"] = doc.pop(pk)
    return doc


def migrate(sqlite_path: str) -> None:
    sq = sqlite3.connect(sqlite_path)
    db.init_db()
    with db.connect() as conn:
        for table, pk in TABLES.items():
            rows = _rows(sq, table)
            coll = conn[table]
            for row in rows:
                doc = _to_doc(row, pk)
                coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)
            if table in INT_ID and rows:
                max_id = max(int(r[pk]) for r in rows)
                conn["counters"].update_one(
                    {"_id": table}, {"$set": {"seq": max_id}}, upsert=True
                )
            print(f"  migrated {table:18} {len(rows)} rows")
    sq.close()


def verify(sqlite_path: str) -> bool:
    sq = sqlite3.connect(sqlite_path)
    ok = True
    with db.connect() as conn:
        for table, pk in TABLES.items():
            rows = _rows(sq, table)
            n_mongo = conn[table].count_documents({})
            status = "OK" if len(rows) == n_mongo else "MISMATCH"
            if len(rows) != n_mongo:
                ok = False
            print(f"  {table:18} sqlite={len(rows):5} mongo={n_mongo:5} {status}")
            # content spot-check
            for row in rows[:SAMPLE]:
                doc = conn[table].find_one({"_id": row[pk]})
                if doc is None:
                    print(f"    MISSING _id={row[pk]} in {table}")
                    ok = False
                    continue
                for col, val in row.items():
                    got = doc.get("_id") if col == pk else doc.get(col)
                    if got != val:
                        print(f"    FIELD MISMATCH {table}._id={row[pk]} {col}: {val!r} != {got!r}")
                        ok = False
        # trace-hash integrity: re-hash a sample of canonical_json
        for row in _rows(sq, "trace_blobs")[:SAMPLE]:
            doc = conn["trace_blobs"].find_one({"_id": row["decision_id"]})
            if doc:
                rehash = "0x" + hashlib.sha256(doc["canonical_json"].encode()).hexdigest()
                if rehash != doc["trace_hash"]:
                    print(f"    TRACE HASH MISMATCH decision_id={row['decision_id']}")
                    ok = False
    sq.close()
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="verify only, no write")
    ap.add_argument("--sqlite", default="data/agent.db")
    args = ap.parse_args()

    print(f"MongoDB target: db={settings.mongo_db_name}")
    if not args.verify:
        print("Migrating...")
        migrate(args.sqlite)
    print("Verifying...")
    if verify(args.sqlite):
        print("\nVERIFY OK — all counts match and spot-checks pass.")
        sys.exit(0)
    else:
        print("\nVERIFY FAILED — DO NOT delete SQLite.")
        sys.exit(1)
```

- [ ] **Step 2: Commit**

```bash
git add tools/migrate_sqlite_to_mongo.py
git commit -m "Add one-time SQLite->Mongo migration + verification script"
```

---

## Task 6: Run the migration against Atlas (manual gate)

**No code — operator step. Requires the real `MONGO_DB_URL` from `.env`.**

- [ ] **Step 1: Run the migration**

Run: `python tools/migrate_sqlite_to_mongo.py`
Expected: per-table "migrated N rows" lines, then a verify table, then `VERIFY OK`. Exit code 0.

- [ ] **Step 2: Sanity-check via the API path**

Run: `python -c "from agent.store import db; conn=db.get_client()[__import__('agent.config',fromlist=['settings']).settings.mongo_db_name]; print('markets', conn['markets'].count_documents({})); print('decisions', conn['decisions'].count_documents({})); print('next decision id', db.next_id(conn,'decisions'))"`
Expected: counts match SQLite (262 markets, 221 decisions), and `next decision id` returns 222 (max+1). (This call increments the counter — re-run the migration's counter seed or note 222 was consumed; harmless for a demo DB.)

- [ ] **Step 3: STOP if verify failed.** Do not proceed to Task 7–9 unless `VERIFY OK`.

---

## Task 7: Run full test suite on Mongo DAO

- [ ] **Step 1: Run everything**

Run: `pytest -q && ruff check . && mypy agent`
Expected: tests PASS, lint clean. Fix any mypy complaints about `Database` typing (e.g. annotate `conn: Database` consistently; add `# type: ignore[index]` only if pymongo stubs require it).

- [ ] **Step 2: Commit any fixups**

```bash
git add -A && git commit -m "Lint/type fixups for Mongo DAO" || echo "nothing to commit"
```

---

## Task 8: Back up the SQLite file

**Operator step — only after Task 6 `VERIFY OK`.**

- [ ] **Step 1: Back up, then remove from the working tree**

```bash
mkdir -p data/backups
cp data/agent.db data/backups/agent.db.20260525
rm -f data/agent.db data/agent.db-wal data/agent.db-shm
ls -la data/backups/
```

Expected: `data/backups/agent.db.20260525` exists; `data/agent.db*` gone.

---

## Task 9: Delete the SQLite integration

**Files:**
- Delete: `agent/store/schema.sql`
- Modify: `agent/config.py` (remove `agent_db_path`)
- Modify: `.env.example` (remove `AGENT_DB_PATH`)
- Grep: confirm no remaining `sqlite3` / `schema.sql` / `agent_db_path` references in `agent/`

- [ ] **Step 1: Delete the schema file**

```bash
git rm agent/store/schema.sql
```

- [ ] **Step 2: Remove `agent_db_path` from config**

In `agent/config.py`, delete the line `agent_db_path: Path = Path("data/agent.db")`. If `Path` is now unused in the file, leave the import (other fields like `agent_log_path` still use it).

- [ ] **Step 3: Remove AGENT_DB_PATH from .env.example**

Delete the `AGENT_DB_PATH=data/agent.db` line.

- [ ] **Step 4: Confirm no dangling references**

Run: `grep -rn "sqlite3\|schema.sql\|agent_db_path\|AGENT_DB_PATH" agent/ tools/ tests/ .env.example`
Expected: only `tools/migrate_sqlite_to_mongo.py` (which legitimately reads SQLite) appears. If anything else shows, fix it.

- [ ] **Step 5: Final verification**

Run: `pytest -q && ruff check . && mypy agent`
Expected: all PASS / clean.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Remove SQLite integration: schema.sql, agent_db_path config"
```

---

## Done

MongoDB is the sole datastore; data migrated and verified; SQLite removed (backup retained at `data/backups/agent.db.20260525`). The migration script stays in `tools/` as a historical/recovery artifact.
