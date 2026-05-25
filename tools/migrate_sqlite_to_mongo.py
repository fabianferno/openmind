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


if __name__ == "__main__":
    main()
