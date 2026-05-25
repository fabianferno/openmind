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
    assert doc is not None  # upsert=True + RETURN AFTER always yields a doc
    return int(doc["seq"])


def _row(doc: dict[str, Any], id_field: str = "id") -> dict[str, Any]:
    """Map a stored doc to the SQLite-era row shape: `_id` -> `id_field`."""
    doc = dict(doc)
    if "_id" in doc:
        doc[id_field] = doc.pop("_id")
    return doc


def _opt(doc: dict[str, Any] | None, id_field: str = "id") -> dict[str, Any] | None:
    """`_row` for a possibly-missing `find_one` result."""
    return _row(doc, id_field) if doc is not None else None


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
    return _opt(conn["markets"].find_one({"_id": market_id}))


def list_resolved_markets(
    conn: Database, *, category: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    q: dict[str, Any] = {"resolved": 1, "resolution_value": {"$ne": None}}
    if category:
        q["category"] = category
    cur = conn["markets"].find(q).sort("end_date", DESCENDING)
    if limit:
        cur = cur.limit(limit)
    return [_row(r) for r in cur]


def list_open_markets(conn: Database, limit: int) -> list[dict[str, Any]]:
    cur = conn["markets"].find({"resolved": 0}).sort("volume_24h", DESCENDING).limit(limit)
    return [_row(r) for r in cur]


def list_tradeable_markets(conn: Database, limit: int) -> list[dict[str, Any]]:
    cur = (
        conn["markets"]
        .find({"resolved": 0, "last_price_yes": {"$gte": 0.05, "$lte": 0.95}})
        .sort("volume_24h", DESCENDING)
        .limit(limit)
    )
    return [_row(r) for r in cur]


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
    return _opt(conn["decisions"].find_one({"_id": decision_id}))


def recent_decisions(
    conn: Database, *, kind: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    q = {"kind": kind} if kind else {}
    cur = conn["decisions"].find(q).sort("_id", DESCENDING).limit(limit)
    return [_row(r) for r in cur]


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
    return [_row(r) for r in cur]


def all_positions(conn: Database, limit: int = 200) -> list[dict[str, Any]]:
    cur = conn["positions"].find().sort("_id", DESCENDING).limit(limit)
    return [_row(r) for r in cur]


def positions_with_market(conn: Database, limit: int = 200) -> list[dict[str, Any]]:
    """Positions newest-first, each enriched with its market `question` and `venue`."""
    rows = [_row(r) for r in conn["positions"].find().sort("_id", DESCENDING).limit(limit)]
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
    return _opt(row)


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
    return [_row(r) for r in cur]


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
    return _opt(conn["breaker_state"].find_one({"_id": name}), "name")


def all_breakers(conn: Database) -> list[dict[str, Any]]:
    return [_row(r, "name") for r in conn["breaker_state"].find()]


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
    return _opt(row)


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
    return [_row(r) for r in rows]


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
    nodes = [_row(r) for r in conn["graph_nodes"].find({"decision_id": decision_id}).sort("_id", 1)]
    edges = [_row(r) for r in conn["graph_edges"].find({"decision_id": decision_id}).sort("_id", 1)]
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
    return _opt(conn["trace_blobs"].find_one({"_id": decision_id}), "decision_id")


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
    return [_row(r) for r in cur]


def recent_anchors(conn: Database, limit: int = 50) -> list[dict[str, Any]]:
    cur = conn["onchain_anchors"].find().sort("_id", DESCENDING).limit(limit)
    return [_row(r) for r in cur]
