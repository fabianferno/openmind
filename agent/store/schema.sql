-- openclob SQLite schema.
-- All timestamps are ISO-8601 UTC strings. All prices are floats in [0,1].
-- Money columns are floats in USD.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------- markets ----------
CREATE TABLE IF NOT EXISTS markets (
    id                TEXT PRIMARY KEY,           -- venue:condition_id
    venue             TEXT NOT NULL,              -- 'polymarket' | 'manifold'
    external_id       TEXT NOT NULL,              -- condition_id or slug
    question          TEXT NOT NULL,
    category          TEXT,
    resolution_source TEXT,
    resolution_rules  TEXT,
    yes_token_id      TEXT,
    no_token_id       TEXT,
    end_date          TEXT,                       -- ISO UTC (scheduled resolution)
    closed_time       TEXT,                       -- ISO UTC (actual close, may be earlier than end_date)
    resolved          INTEGER NOT NULL DEFAULT 0, -- 0/1
    resolution_value  REAL,                       -- 1.0 YES / 0.0 NO / null unresolved
    last_price_yes    REAL,
    volume_24h        REAL,
    book_depth_5c     REAL,
    seen_at           TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    raw               TEXT                        -- raw JSON, debugging
);

CREATE INDEX IF NOT EXISTS idx_markets_venue_ext ON markets(venue, external_id);
CREATE INDEX IF NOT EXISTS idx_markets_resolved ON markets(resolved, end_date);
CREATE INDEX IF NOT EXISTS idx_markets_category ON markets(category);

-- ---------- decisions ----------
-- Every reasoning call. Append-only.
CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id     TEXT NOT NULL,
    kind          TEXT NOT NULL,                  -- 'ambiguity' | 'entry' | 'exit'
    as_of         TEXT NOT NULL,                  -- temporal-guard time
    prompt        TEXT NOT NULL,
    search_used   TEXT,                           -- JSON list of {url, title, published}
    model_id      TEXT NOT NULL,
    response_raw  TEXT NOT NULL,                  -- raw LLM response
    response_json TEXT,                           -- parsed structured output
    p_yes         REAL,
    confidence    REAL,
    action        TEXT,                           -- 'enter_yes' | 'enter_no' | 'hold' | 'sell' | 'skip'
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_market ON decisions(market_id, kind, created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_day ON decisions(substr(created_at, 1, 10));

-- ---------- positions ----------
CREATE TABLE IF NOT EXISTS positions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id           TEXT NOT NULL,
    venue               TEXT NOT NULL,
    side                TEXT NOT NULL,            -- 'YES' | 'NO'
    shares              REAL NOT NULL,
    entry_price         REAL NOT NULL,
    exit_price          REAL,
    notional_in         REAL NOT NULL,
    notional_out        REAL,
    pnl                 REAL,
    fees                REAL NOT NULL DEFAULT 0,
    status              TEXT NOT NULL,            -- 'open' | 'closed' | 'cancelled'
    entry_decision_id   INTEGER,
    exit_decision_id    INTEGER,
    venue_entry_order   TEXT,                     -- order id at venue
    venue_exit_order    TEXT,
    p_yes_at_entry      REAL,
    p_yes_at_exit       REAL,
    opened_at           TEXT NOT NULL,
    closed_at           TEXT,
    FOREIGN KEY (market_id) REFERENCES markets(id),
    FOREIGN KEY (entry_decision_id) REFERENCES decisions(id),
    FOREIGN KEY (exit_decision_id)  REFERENCES decisions(id)
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_market ON positions(market_id);

-- ---------- pending orders ----------
-- Maker orders that haven't filled yet. Tracked so we can cancel stale ones.
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id     TEXT NOT NULL,
    venue         TEXT NOT NULL,
    venue_order_id TEXT,
    side          TEXT NOT NULL,                  -- 'YES' | 'NO'
    order_type    TEXT NOT NULL,                  -- 'maker' | 'taker'
    limit_price   REAL NOT NULL,
    requested_size REAL NOT NULL,
    filled_size   REAL NOT NULL DEFAULT 0,
    status        TEXT NOT NULL,                  -- 'open' | 'filled' | 'partial' | 'cancelled' | 'expired'
    decision_id   INTEGER,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    closed_at     TEXT,
    FOREIGN KEY (market_id) REFERENCES markets(id),
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, expires_at);

-- ---------- metrics ----------
-- Rolling per-category and overall Brier/ECE/PnL/calibration multiplier.
CREATE TABLE IF NOT EXISTS metrics (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of            TEXT NOT NULL,
    category         TEXT NOT NULL,               -- 'overall' or category name
    n_resolved       INTEGER NOT NULL DEFAULT 0,
    brier            REAL,
    ece              REAL,
    realized_pnl     REAL NOT NULL DEFAULT 0,
    realized_roi     REAL,
    calibration_mul  REAL NOT NULL DEFAULT 0.5,
    UNIQUE (as_of, category)
);

-- ---------- llm budget ledger ----------
CREATE TABLE IF NOT EXISTS llm_usage (
    day            TEXT PRIMARY KEY,              -- YYYY-MM-DD UTC
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_usd       REAL NOT NULL DEFAULT 0
);

-- ---------- circuit-breaker state ----------
CREATE TABLE IF NOT EXISTS breaker_state (
    name         TEXT PRIMARY KEY,                -- 'daily_loss' | 'api_failures' | 'manual'
    tripped      INTEGER NOT NULL DEFAULT 0,
    tripped_at   TEXT,
    expires_at   TEXT,
    reason       TEXT
);

-- ---------- backtest snapshots ----------
-- Price/orderbook snapshots used by the backtester for resolved markets.
CREATE TABLE IF NOT EXISTS market_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id   TEXT NOT NULL,
    as_of       TEXT NOT NULL,
    price_yes   REAL NOT NULL,
    book_depth_5c REAL,
    volume_24h  REAL,
    raw         TEXT,
    UNIQUE (market_id, as_of),
    FOREIGN KEY (market_id) REFERENCES markets(id)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_market_time ON market_snapshots(market_id, as_of);

-- ---------- blocklist ----------
CREATE TABLE IF NOT EXISTS blocklist (
    pattern    TEXT PRIMARY KEY,                  -- substring or regex; matched against question
    reason     TEXT,
    added_at   TEXT NOT NULL
);

-- ===================================================================
-- openmind: GraphRAG + on-chain (Arc) extensions
-- ===================================================================

-- ---------- graph runs ----------
-- One row per ontology+graph build, tied to the entry decision it informed.
CREATE TABLE IF NOT EXISTS graph_runs (
    decision_id   INTEGER PRIMARY KEY,
    market_id     TEXT NOT NULL,
    as_of         TEXT NOT NULL,
    ontology_json TEXT NOT NULL,                  -- {entity_types:[...], relation_types:[...]}
    stats_json    TEXT NOT NULL,                  -- {node_count, edge_count, type_counts, central}
    created_at    TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(id),
    FOREIGN KEY (market_id)   REFERENCES markets(id)
);

-- ---------- graph nodes ----------
CREATE TABLE IF NOT EXISTS graph_nodes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id    INTEGER NOT NULL,
    market_id      TEXT NOT NULL,
    node_key       TEXT NOT NULL,                 -- stable slug within this graph
    label          TEXT NOT NULL,
    type           TEXT NOT NULL,                 -- entity type (PascalCase)
    summary        TEXT,
    source_url     TEXT,
    published_date TEXT,
    degree         INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
CREATE INDEX IF NOT EXISTS idx_gnodes_decision ON graph_nodes(decision_id);

-- ---------- graph edges ----------
CREATE TABLE IF NOT EXISTS graph_edges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id    INTEGER NOT NULL,
    market_id      TEXT NOT NULL,
    source_key     TEXT NOT NULL,
    target_key     TEXT NOT NULL,
    type           TEXT NOT NULL,                 -- relation type (UPPER_SNAKE_CASE)
    rationale      TEXT,
    source_url     TEXT,
    published_date TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
CREATE INDEX IF NOT EXISTS idx_gedges_decision ON graph_edges(decision_id);

-- ---------- reasoning-trace blobs ----------
-- The exact canonical bytes that were hashed, so the UI can re-hash and verify.
CREATE TABLE IF NOT EXISTS trace_blobs (
    decision_id   INTEGER PRIMARY KEY,
    market_id     TEXT NOT NULL,
    trace_hash    TEXT NOT NULL,                  -- 0x… sha256 of canonical_json
    canonical_json TEXT NOT NULL,                 -- the exact string hashed
    created_at    TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);

-- ---------- on-chain anchors / settlements (Arc) ----------
CREATE TABLE IF NOT EXISTS onchain_anchors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id   INTEGER,
    market_id     TEXT,
    kind          TEXT NOT NULL,                  -- 'anchor' | 'settle'
    trace_hash    TEXT,
    tx_hash       TEXT NOT NULL,
    explorer_url  TEXT,
    usdc_amount   REAL,
    to_address    TEXT,
    network       TEXT NOT NULL DEFAULT 'arc-testnet',
    mocked        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
CREATE INDEX IF NOT EXISTS idx_anchors_decision ON onchain_anchors(decision_id);
