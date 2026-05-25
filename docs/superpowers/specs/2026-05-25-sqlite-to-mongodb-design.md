# SQLite → MongoDB Migration — Design

Date: 2026-05-25
Status: Approved

## Goal

Replace SQLite with MongoDB (Atlas, database name `openmind`) as openclob's
persistence layer. Migrate all existing data losslessly, verify no loss, then
remove the SQLite integration entirely.

Hard requirements:
- Preserve integer record IDs (used as foreign keys and in API URLs like
  `/api/decisions/{id}`).
- Preserve every DAO function's return contract so the FastAPI layer, the
  Next.js frontend, and on-chain reasoning-trace hashes keep working unchanged.
- Do not delete SQLite until the data migration verifies clean (counts +
  content spot-check).

## Current state (surveyed)

- `agent/store/db.py` — thin DAO, ~30 functions, each takes a
  `sqlite3.Connection` as first arg. `connect()` is a context manager.
- `agent/store/schema.sql` — 14 tables, source of truth for schema.
- 71 `with db.connect() as conn:` call sites across 20 files; all use DAO
  functions except 12 raw-SQL sites.
- `sqlite3` is imported only in `db.py`.
- The Next.js frontend never touches the DB directly — only via the FastAPI
  server in `agent/api/server.py`.
- Data volume (~2,900 docs): markets 262, decisions 221, positions 31,
  orders 8, llm_usage 2, market_snapshots 705, graph_runs 32, graph_nodes 272,
  graph_edges 203, trace_blobs 33, onchain_anchors 44. (metrics, breaker_state,
  blocklist empty.)

Tables with `AUTOINCREMENT` int PK: decisions, positions, orders, metrics,
market_snapshots, graph_nodes, graph_edges, onchain_anchors.
Tables with natural PK: markets(id), llm_usage(day), breaker_state(name),
blocklist(pattern), graph_runs(decision_id), trace_blobs(decision_id).

## Design

### 1. Keep the interface, swap the engine
`db.connect()` remains a context manager but yields a
`pymongo.database.Database` instead of a `sqlite3.Connection`. All 30 DAO
functions keep their signatures (`conn` first arg) and return shapes, so the 71
call sites that only use the DAO are untouched. Only `db.py` internals, the 12
raw-SQL sites, config, and tests change.

A module-level cached `MongoClient` (lazy singleton) provides proper Atlas
connection pooling. `connect()` yields `client[mongo_db_name]` and does **not**
close the client on exit.

### 2. Integer IDs via a `counters` collection
`counters` docs: `{_id: "<table>", seq: N}`. `next_id(conn, name)` uses
`find_one_and_update({_id:name}, {$inc:{seq:1}}, upsert=True,
return_document=AFTER)`. AUTOINCREMENT tables use the issued int as `_id`.
Natural-key tables use that key as `_id`. `record_decision`, `open_position`,
`record_order`, `record_anchor` return the same `int` as today.

### 3. Faithful field shapes (critical)
JSON-text columns (`raw`, `search_used`, `response_json`, `ontology_json`,
`stats_json`, `canonical_json`) are stored **as strings**, exactly as SQLite
held them:
- `get_graph` keeps `json.loads`-ing ontology/stats → identical dicts returned.
- `canonical_json` is the exact byte string sha256'd and anchored on-chain;
  verbatim storage keeps every trace hash verifiable.
- The frontend receives byte-identical payloads.
Boolean-as-int columns (`resolved`, `tripped`, `mocked`) stay `0/1` ints.

### 4. Raw SQL → new DAO functions
The 12 raw-SQL sites move into named `db.py` functions:
- `agent/monitor/positions.py:18` → `latest_prior_p_yes(conn, market_id)`
- `agent/__main__.py:168` (block cmd) → `add_blocklist(conn, pattern, reason)`
- `agent/api/server.py:84,177,287` → `list_open_markets(conn, limit)`,
  `list_tradeable_markets(conn, limit)`, `positions_with_market(conn, limit)`
  (positions⋈markets join performed in Python — tiny dataset, mongomock-safe).
- `agent/backtest/harness.py:122,138` → `latest_open_position_for_market(conn, market_id)`,
  `simulated_closed_pnl(conn)`
- `agent/strategy/calibration.py:82,100` → `recent_decisions_for_market(conn, market_id, kind, limit)`,
  `closed_pnl_for_markets(conn, market_ids)`
- `tests/conftest.py:37` → `clear_breakers(conn)`

### 5. `init_db()` builds collections + indexes
Replaces `schema.sql` execution. Indexes mirror current SQLite indexes:
- markets: `(venue, external_id)`, `(resolved, end_date)`, `category`
- decisions: `(market_id, kind, created_at)`
- positions: `status`, `market_id`
- orders: `(status, expires_at)`
- market_snapshots: **unique** `(market_id, as_of)`
- metrics: **unique** `(as_of, category)`
- graph_nodes: `decision_id`; graph_edges: `decision_id`
- onchain_anchors: `decision_id`
`insert_snapshot`'s `INSERT OR IGNORE` → `update_one(filter, {$setOnInsert:...},
upsert=True)`.

### 6. Config
Add to `agent/config.py`: `mongo_db_url: str`, `mongo_db_name: str = "openmind"`
(read via `settings`). `.env.example` gains `MONGO_DB_URL=` and
`MONGO_DB_NAME=openmind`. `agent_db_path` removed in the deletion phase.

### 7. One-time migration + verification — `tools/migrate_sqlite_to_mongo.py`
1. Read `data/agent.db`.
2. Upsert every row into Mongo with identical `_id`s (idempotent), mapping
   columns per the field-shape rules above.
3. Seed each counter to `max(_id)` for AUTOINCREMENT tables.
4. **Verify**: per-table count equality + per-collection content spot-check
   (sample rows, compare every field incl. JSON blobs).
5. Abort and report on any mismatch; print a summary table on success.

### 8. Deletion phase (only after verification passes)
- Remove `sqlite3` import and all SQLite code from `db.py`.
- Delete `agent/store/schema.sql`.
- Remove `agent_db_path` from `config.py` and `.env.example`.
- Add `pymongo` to deps; add `mongomock` to dev deps.
- Back up `data/agent.db` → `data/backups/agent.db.20260525`, then remove
  `data/agent.db{,-wal,-shm}` from the working tree.

### 9. Tests (TDD)
- Add `mongomock` so the suite runs offline.
- `conftest.py` monkeypatches the cached client to a mongomock client;
  `fresh_db` gives each test a clean in-memory DB.
- `test_db_roundtrips.py` raw SELECTs rewritten to use DAO functions.
- The real Atlas path is exercised once via the migration script against the
  actual `MONGO_DB_URL`.

## Risks / mitigations
- **Trace-hash integrity**: `canonical_json` stored verbatim → hashes still
  verify. Spot-check includes re-hashing a sample.
- **Atlas connection churn**: single cached `MongoClient`, never closed per call.
- **mongomock aggregation gaps**: joins done in Python, not `$lookup`.
- **Lossy migration**: counts + field-level spot-check gate the deletion.

## Sequencing
config+deps → mongo DAO (TDD) → rewrite raw-SQL sites → migration+verify script
→ run migration against Atlas, confirm clean → deletion phase → full test run.
