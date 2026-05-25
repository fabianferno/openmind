# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`openclob` — autonomous prediction-market trading agent (Polymarket + Manifold) driven by an LLM reasoning loop (Claude via AWS Bedrock) and Tavily search. Phased build: backtest → paper (Manifold) → dryrun (Polymarket, no orders sent) → live. Phase transitions are gated by pre-committed metrics in `prd.md` §3 (Brier, ECE, ROI, sample size, leakage check). Read `prd.md` before non-trivial design changes — it is the source of truth for what the system is supposed to do and why.

## Setup & commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # fill in keys
mkdir -p data logs
python -m agent init-db
```

Run / operate:

```bash
python -m agent cycle              # one cycle (cron-friendly)
python -m agent loop                # forever, sleeps AGENT_CYCLE_SECONDS
python -m agent backtest --days 7 --limit 300
python -m agent leakage-check --limit 100   # Phase-1 gate; exits 2 on fail
python -m agent hydrate-history --target 500
python -m agent recompute-metrics
python -m agent report [--json]
python -m agent block <pattern>
python -m agent trip-breaker <reason> | reset-breaker
```

The CLI is also installed as the `openclob` console script. Mode is set by `AGENT_MODE` env var (`backtest|paper|dryrun|live`); `paper` uses Manifold, the other live-ish modes use Polymarket.

Dev:

```bash
pytest                              # full suite
pytest tests/test_safety.py -q      # single file
pytest tests/test_safety.py::test_name
ruff check . && ruff format .
mypy agent
```

## Architecture

### Cycle (`agent/agent.py::run_cycle`)
Each cycle: (1) check circuit breakers — if any tripped, halt and alert; (2) cancel stale orders (live only); (3) re-evaluate every open position via `monitor/positions.py`; (4) discover candidate markets (Manifold in paper, Polymarket Gamma + CLOB book depth otherwise); (5) for each candidate run `strategy/filters.py` then `strategy/entry.py::plan_entry` (which calls the LLM); (6) place entries through the mode-specific executor. `MAX_CANDIDATES_PER_CYCLE = 20` bounds LLM cost per cycle. `run_loop` simply repeats `run_cycle` on a `time.sleep(AGENT_CYCLE_SECONDS)` interval.

### Layered packages
- `agent/data/` — market clients: `manifold.py`, `polymarket_gamma.py` (discovery), `polymarket_clob.py` (orderbook + signed orders), `historical.py` (hydration of resolved markets for backtests). All clients normalise to a common market dict that gets upserted via `store/db.py::upsert_market`.
- `agent/reasoning/` — `claude_client.py` (Bedrock wrapper with per-decision and per-day USD caps), `search.py` (Tavily with date-bounded queries), `prompts.py` (ambiguity check + entry/exit reasoning), `temporal_guard.py` (rejects search results published after a market's reasoning cutoff — this is what `leakage-check` validates).
- `agent/strategy/` — `filters.py` (liquidity / category / blocklist pre-filter, cheap), `entry.py` (LLM-driven entry plan), `exit.py` (LLM-driven exit decisions on open positions), `sizing.py` (Kelly-ish with category calibration), `calibration.py` (per-category Brier/ECE → multiplier on bet size).
- `agent/execution/` — `paper.py` (`ManifoldExecutor`), `live.py` (`LiveExecutor` for Polymarket; the same class handles `dryrun` by short-circuiting submission), `safety.py` (hard-coded breakers — daily loss cap, max open positions, per-market cap, slippage guard, API-failure cooldown, manual trip. The LLM cannot bypass these).
- `agent/backtest/` — `harness.py` (replays cached snapshots), `leakage_check.py` (Phase 1 gate), `metrics.py` (Brier/ECE/ROI).
- `agent/monitor/` — `positions.py` (re-eval loop), `report.py` (daily report numbers — same metrics the gates check), `alerts.py` (webhook).
- `agent/store/` — `schema.sql` is the source of truth for the SQLite schema; `db.py` is a thin DAO. All persistence goes through `db.connect()`.
- `agent/config.py` — `settings` is a pydantic-settings singleton; **import `settings` from `agent.config` rather than reading `os.environ` directly** (existing convention).

### Discovery cost-shaping
Polymarket discovery is two-staged: cheap Gamma list → `filters.passes_all` → only survivors get a CLOB book-depth fetch (expensive). Preserve this ordering when adding filters — putting an expensive check before the pre-filter inflates API cost per cycle linearly with market count.

### Modes and executors
The `agent_mode` setting selects both data source and executor:

| mode      | discovery        | executor              | orders sent |
|-----------|------------------|-----------------------|-------------|
| backtest  | cached snapshots | (harness, not loop)   | no          |
| paper     | Manifold         | `ManifoldExecutor`    | play-money  |
| dryrun    | Polymarket       | `LiveExecutor` (dry)  | signed, not submitted |
| live      | Polymarket       | `LiveExecutor`        | yes         |

### Safety invariants
- Breakers in `execution/safety.py` are **not bypassable by the LLM**. New limits go here, not in prompts.
- Decisions and outcomes are logged to SQLite so calibration can recompute; don't add ephemeral state that bypasses the DB.
- `temporal_guard` ensures backtests use only information available before a market's cutoff. Any new search/data path must go through it or document why it can't leak.
