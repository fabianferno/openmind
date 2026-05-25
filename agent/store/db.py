"""SQLite DAO. Thin wrapper around sqlite3 with typed dict rows."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection. `with connect() as conn:` usage."""
    db_path = Path(path or settings.agent_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db(path: Path | None = None) -> None:
    sql = SCHEMA_PATH.read_text()
    with connect(path) as conn:
        conn.executescript(sql)


# ---------- markets ----------

def upsert_market(conn: sqlite3.Connection, m: dict[str, Any]) -> str:
    """Upsert market row. `m` must include venue, external_id, question."""
    market_id = m.get("id") or f"{m['venue']}:{m['external_id']}"
    now = _now()
    conn.execute(
        """
        INSERT INTO markets (
            id, venue, external_id, question, category, resolution_source, resolution_rules,
            yes_token_id, no_token_id, end_date, closed_time, resolved, resolution_value,
            last_price_yes, volume_24h, book_depth_5c, seen_at, updated_at, raw
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            question = excluded.question,
            category = excluded.category,
            resolution_source = excluded.resolution_source,
            resolution_rules = excluded.resolution_rules,
            yes_token_id = excluded.yes_token_id,
            no_token_id = excluded.no_token_id,
            end_date = excluded.end_date,
            closed_time = excluded.closed_time,
            resolved = excluded.resolved,
            resolution_value = excluded.resolution_value,
            last_price_yes = excluded.last_price_yes,
            volume_24h = excluded.volume_24h,
            book_depth_5c = excluded.book_depth_5c,
            updated_at = excluded.updated_at,
            raw = excluded.raw
        """,
        (
            market_id,
            m["venue"],
            m["external_id"],
            m["question"],
            m.get("category"),
            m.get("resolution_source"),
            m.get("resolution_rules"),
            m.get("yes_token_id"),
            m.get("no_token_id"),
            m.get("end_date"),
            m.get("closed_time"),
            1 if m.get("resolved") else 0,
            m.get("resolution_value"),
            m.get("last_price_yes"),
            m.get("volume_24h"),
            m.get("book_depth_5c"),
            now,
            now,
            json.dumps(m.get("raw")) if m.get("raw") else None,
        ),
    )
    return market_id


def get_market(conn: sqlite3.Connection, market_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM markets WHERE id = ?", (market_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_resolved_markets(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM markets WHERE resolved = 1 AND resolution_value IS NOT NULL"
    args: list[Any] = []
    if category:
        sql += " AND category = ?"
        args.append(category)
    sql += " ORDER BY end_date DESC"
    if limit:
        sql += " LIMIT ?"
        args.append(limit)
    return [_row_to_dict(r) for r in conn.execute(sql, args).fetchall()]


# ---------- decisions ----------

def record_decision(conn: sqlite3.Connection, d: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO decisions (
            market_id, kind, as_of, prompt, search_used, model_id,
            response_raw, response_json, p_yes, confidence, action,
            input_tokens, output_tokens, cost_usd, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            d["market_id"],
            d["kind"],
            d["as_of"],
            d["prompt"],
            json.dumps(d.get("search_used")) if d.get("search_used") is not None else None,
            d["model_id"],
            d["response_raw"],
            json.dumps(d.get("response_json")) if d.get("response_json") is not None else None,
            d.get("p_yes"),
            d.get("confidence"),
            d.get("action"),
            d.get("input_tokens", 0),
            d.get("output_tokens", 0),
            d.get("cost_usd", 0.0),
            _now(),
        ),
    )
    return int(cur.lastrowid)


# ---------- positions ----------

def open_position(conn: sqlite3.Connection, p: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO positions (
            market_id, venue, side, shares, entry_price, notional_in,
            status, entry_decision_id, venue_entry_order, p_yes_at_entry, opened_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
        """,
        (
            p["market_id"],
            p["venue"],
            p["side"],
            p["shares"],
            p["entry_price"],
            p["notional_in"],
            p.get("entry_decision_id"),
            p.get("venue_entry_order"),
            p.get("p_yes_at_entry"),
            _now(),
        ),
    )
    return int(cur.lastrowid)


def close_position(
    conn: sqlite3.Connection,
    pos_id: int,
    *,
    exit_price: float,
    notional_out: float,
    exit_decision_id: int | None,
    venue_exit_order: str | None,
    p_yes_at_exit: float | None,
    fees: float = 0.0,
) -> None:
    conn.execute(
        """
        UPDATE positions
           SET exit_price = ?, notional_out = ?, pnl = ? - notional_in - ?, fees = fees + ?,
               status = 'closed', exit_decision_id = ?, venue_exit_order = ?,
               p_yes_at_exit = ?, closed_at = ?
         WHERE id = ?
        """,
        (
            exit_price,
            notional_out,
            notional_out,
            fees,
            fees,
            exit_decision_id,
            venue_exit_order,
            p_yes_at_exit,
            _now(),
            pos_id,
        ),
    )


def open_positions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM positions WHERE status = 'open' ORDER BY opened_at"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def positions_today_pnl(conn: sqlite3.Connection) -> float:
    today = datetime.now(UTC).date().isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) AS pnl FROM positions "
        "WHERE status = 'closed' AND substr(closed_at, 1, 10) = ?",
        (today,),
    ).fetchone()
    return float(row["pnl"]) if row else 0.0


# ---------- orders ----------

def record_order(conn: sqlite3.Connection, o: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO orders (
            market_id, venue, venue_order_id, side, order_type,
            limit_price, requested_size, status, decision_id,
            created_at, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            o["market_id"],
            o["venue"],
            o.get("venue_order_id"),
            o["side"],
            o["order_type"],
            o["limit_price"],
            o["requested_size"],
            o.get("status", "open"),
            o.get("decision_id"),
            _now(),
            o["expires_at"],
        ),
    )
    return int(cur.lastrowid)


def open_orders(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        _row_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM orders WHERE status IN ('open', 'partial') ORDER BY created_at"
        ).fetchall()
    ]


def update_order(conn: sqlite3.Connection, order_id: int, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE orders SET {sets} WHERE id = ?", (*fields.values(), order_id))


# ---------- llm budget ----------

def add_llm_usage(conn: sqlite3.Connection, input_tokens: int, output_tokens: int, cost: float) -> None:
    day = datetime.now(UTC).date().isoformat()
    conn.execute(
        """
        INSERT INTO llm_usage (day, input_tokens, output_tokens, cost_usd)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(day) DO UPDATE SET
            input_tokens  = input_tokens  + excluded.input_tokens,
            output_tokens = output_tokens + excluded.output_tokens,
            cost_usd      = cost_usd      + excluded.cost_usd
        """,
        (day, input_tokens, output_tokens, cost),
    )


def llm_cost_today(conn: sqlite3.Connection) -> float:
    day = datetime.now(UTC).date().isoformat()
    row = conn.execute("SELECT cost_usd FROM llm_usage WHERE day = ?", (day,)).fetchone()
    return float(row["cost_usd"]) if row else 0.0


# ---------- breakers ----------

def set_breaker(conn: sqlite3.Connection, name: str, *, tripped: bool, reason: str | None = None,
                expires_at: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO breaker_state (name, tripped, tripped_at, expires_at, reason)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            tripped = excluded.tripped,
            tripped_at = excluded.tripped_at,
            expires_at = excluded.expires_at,
            reason = excluded.reason
        """,
        (name, 1 if tripped else 0, _now() if tripped else None, expires_at, reason),
    )


def breaker_status(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM breaker_state WHERE name = ?", (name,)).fetchone()
    return _row_to_dict(row) if row else None


def all_breakers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in conn.execute("SELECT * FROM breaker_state").fetchall()]


# ---------- snapshots ----------

def insert_snapshot(conn: sqlite3.Connection, s: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO market_snapshots
            (market_id, as_of, price_yes, book_depth_5c, volume_24h, raw)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            s["market_id"],
            s["as_of"],
            s["price_yes"],
            s.get("book_depth_5c"),
            s.get("volume_24h"),
            json.dumps(s.get("raw")) if s.get("raw") else None,
        ),
    )


def snapshot_at_or_before(
    conn: sqlite3.Connection, market_id: str, as_of: str
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM market_snapshots
         WHERE market_id = ? AND as_of <= ?
         ORDER BY as_of DESC LIMIT 1
        """,
        (market_id, as_of),
    ).fetchone()
    return _row_to_dict(row) if row else None


# ---------- metrics ----------

def upsert_metrics(conn: sqlite3.Connection, m: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO metrics (as_of, category, n_resolved, brier, ece, realized_pnl,
                             realized_roi, calibration_mul)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(as_of, category) DO UPDATE SET
            n_resolved = excluded.n_resolved,
            brier = excluded.brier,
            ece = excluded.ece,
            realized_pnl = excluded.realized_pnl,
            realized_roi = excluded.realized_roi,
            calibration_mul = excluded.calibration_mul
        """,
        (
            m["as_of"],
            m["category"],
            m["n_resolved"],
            m.get("brier"),
            m.get("ece"),
            m.get("realized_pnl", 0.0),
            m.get("realized_roi"),
            m.get("calibration_mul", 0.5),
        ),
    )


def latest_calibration_multipliers(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT category, calibration_mul
          FROM metrics
         WHERE as_of = (SELECT MAX(as_of) FROM metrics AS m2 WHERE m2.category = metrics.category)
        """
    ).fetchall()
    return {r["category"]: float(r["calibration_mul"]) for r in rows}


# ---------- blocklist ----------

def in_blocklist(conn: sqlite3.Connection, question: str) -> bool:
    q = question.lower()
    rows = conn.execute("SELECT pattern FROM blocklist").fetchall()
    return any(r["pattern"].lower() in q for r in rows)


# ---------- graphrag ----------

def save_graph(
    conn: sqlite3.Connection,
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
    conn.execute("DELETE FROM graph_nodes WHERE decision_id = ?", (decision_id,))
    conn.execute("DELETE FROM graph_edges WHERE decision_id = ?", (decision_id,))
    conn.execute(
        """
        INSERT INTO graph_runs (decision_id, market_id, as_of, ontology_json, stats_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(decision_id) DO UPDATE SET
            ontology_json = excluded.ontology_json, stats_json = excluded.stats_json
        """,
        (decision_id, market_id, as_of, json.dumps(ontology), json.dumps(stats), now),
    )
    for n in nodes:
        conn.execute(
            """
            INSERT INTO graph_nodes
                (decision_id, market_id, node_key, label, type, summary,
                 source_url, published_date, degree, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id, market_id, n["id"], n["label"], n["type"],
                n.get("summary"), n.get("source_url"), n.get("published_date"),
                int(n.get("degree", 0)), now,
            ),
        )
    for e in edges:
        conn.execute(
            """
            INSERT INTO graph_edges
                (decision_id, market_id, source_key, target_key, type, rationale,
                 source_url, published_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id, market_id, e["source"], e["target"], e["type"],
                e.get("rationale"), e.get("source_url"), e.get("published_date"), now,
            ),
        )


def get_graph(conn: sqlite3.Connection, decision_id: int) -> dict[str, Any] | None:
    run = conn.execute(
        "SELECT * FROM graph_runs WHERE decision_id = ?", (decision_id,)
    ).fetchone()
    if not run:
        return None
    nodes = [
        _row_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM graph_nodes WHERE decision_id = ? ORDER BY id", (decision_id,)
        ).fetchall()
    ]
    edges = [
        _row_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM graph_edges WHERE decision_id = ? ORDER BY id", (decision_id,)
        ).fetchall()
    ]
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
    conn: sqlite3.Connection,
    *,
    decision_id: int,
    market_id: str,
    trace_hash: str,
    canonical_json: str,
) -> None:
    conn.execute(
        """
        INSERT INTO trace_blobs (decision_id, market_id, trace_hash, canonical_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(decision_id) DO UPDATE SET
            trace_hash = excluded.trace_hash, canonical_json = excluded.canonical_json
        """,
        (decision_id, market_id, trace_hash, canonical_json, _now()),
    )


def get_trace_blob(conn: sqlite3.Connection, decision_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM trace_blobs WHERE decision_id = ?", (decision_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


# ---------- on-chain anchors ----------

def record_anchor(conn: sqlite3.Connection, a: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO onchain_anchors
            (decision_id, market_id, kind, trace_hash, tx_hash, explorer_url,
             usdc_amount, to_address, network, mocked, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            a.get("decision_id"), a.get("market_id"), a["kind"], a.get("trace_hash"),
            a["tx_hash"], a.get("explorer_url"), a.get("usdc_amount"), a.get("to_address"),
            a.get("network", "arc-testnet"), 1 if a.get("mocked") else 0, _now(),
        ),
    )
    return int(cur.lastrowid)


def anchors_for_decision(conn: sqlite3.Connection, decision_id: int) -> list[dict[str, Any]]:
    return [
        _row_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM onchain_anchors WHERE decision_id = ? ORDER BY id", (decision_id,)
        ).fetchall()
    ]


def recent_anchors(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    return [
        _row_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM onchain_anchors ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    ]


# ---------- read helpers for the API ----------

def get_decision(conn: sqlite3.Connection, decision_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
    return _row_to_dict(row) if row else None


def recent_decisions(
    conn: sqlite3.Connection, *, kind: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM decisions"
    args: list[Any] = []
    if kind:
        sql += " WHERE kind = ?"
        args.append(kind)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return [_row_to_dict(r) for r in conn.execute(sql, args).fetchall()]


def all_positions(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    return [
        _row_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM positions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    ]


def latest_metrics(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM metrics
         WHERE as_of = (SELECT MAX(as_of) FROM metrics AS m2 WHERE m2.category = metrics.category)
         ORDER BY category
        """
    ).fetchall()
    return [_row_to_dict(r) for r in rows]
