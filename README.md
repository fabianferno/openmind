# openclob

Autonomous prediction-market trading agent for **Polymarket** and **Manifold**, driven by an
LLM reasoning loop (Claude via AWS Bedrock) and date-bounded web search (Tavily).

The agent fetches markets, reasons about them with information available *as of* a chosen point
in time, takes positions, monitors them every cycle, and exits — treating YES/NO shares as
continuously-priced assets rather than fixed-odds bets. Real money is the **last** step, not the
first: the build is phased and each phase transition is gated on pre-committed metrics.

See [`prd.md`](./prd.md) for the full goals, strategy, gates, and phased build plan — it is the
source of truth for *what* the system does and *why*. Read it before any non-trivial design change.

> **Not financial advice.** This is a skill-validation exercise with optional small-stakes
> deployment ($20–50 bankroll). It is not designed to be reliably profitable.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env             # then fill in keys
mkdir -p data logs

# initialise the SQLite schema
python -m agent init-db
```

The CLI is also installed as the `openclob` console script (`openclob init-db`, etc.).

## Modes

`AGENT_MODE` selects both the data source and the executor:

| mode       | discovery          | executor                  | orders sent             |
|------------|--------------------|---------------------------|-------------------------|
| `backtest` | cached snapshots   | harness (not the loop)    | no                      |
| `paper`    | Manifold           | `ManifoldExecutor`        | play-money              |
| `dryrun`   | Polymarket         | `LiveExecutor` (dry path) | signed, **not** submitted |
| `live`     | Polymarket         | `LiveExecutor`            | yes (maker-first limit) |

## Running the agent

```bash
# one cycle (cron-friendly) — prints a JSON summary
python -m agent cycle

# run forever, sleeping AGENT_CYCLE_SECONDS between cycles (override with --period)
python -m agent loop [--period 1200]
```

A cycle (`agent/agent.py::run_cycle`): check circuit breakers → cancel stale orders (live only)
→ re-evaluate every open position → discover candidate markets → pre-filter, ambiguity-check,
and run entry reasoning on each → place entries via the mode's executor. `MAX_CANDIDATES_PER_CYCLE`
(20) bounds LLM cost per cycle.

## Backtesting

The backtest replays cached snapshots of resolved markets, so you must hydrate history first.
Manifold is the default source (it keeps full bet history; Polymarket purges after ~6 weeks).

```bash
# pull resolved markets + price snapshots into the DB
python -m agent hydrate-history --target 500
python -m agent hydrate-history --source polymarket --target 500 --tag 2:politics

# replay: sample N days before resolution, score reasoning against the actual outcome
python -m agent backtest --days 7 --limit 300 [--category geopolitics]

# Phase-1 gate: rerun with intentionally broken date bounds. If the leaky Brier
# isn't dramatically better (delta >= 0.05), leak prevention is broken. Exits 2 on fail.
python -m agent leakage-check --days 7 --limit 100
```

If the agent can't beat the market baseline in backtest, the project ends there — no proceeding
to paper trading "to see what happens".

## Operating & monitoring

```bash
python -m agent report [--json]      # daily report — the same metrics the gates check
python -m agent recompute-metrics    # recompute per-category Brier/ECE/ROI/calibration
python -m agent block <pattern>      # add a substring to the blocklist (matched on the question)
python -m agent trip-breaker <reason>  # manually halt trading
python -m agent reset-breaker          # clear the manual breaker
```

## Gates between phases

Phase transitions are pre-committed and metric-gated, not vibes-based — see §3 of `prd.md`.
The thresholds tighten as real money comes into play:

| metric (gate)                | backtest      | paper         | real money            |
|------------------------------|---------------|---------------|-----------------------|
| sample size (resolved)       | ≥ 300         | ≥ 100         | ongoing               |
| Brier score                  | ≤ 0.15        | ≤ 0.17        | ≤ 0.17 (trailing 50)  |
| ECE                          | ≤ 0.05        | ≤ 0.07        | ≤ 0.08 (trailing 50)  |
| ROI after fees               | > 0%          | > 0%          | > 0% over 30 days     |
| per-category Brier           | ≤ 0.18        | ≤ 0.18        | ≤ 0.18                |
| temporal leakage check       | passes        | n/a           | n/a                   |

`report` and `leakage-check` print the relevant numbers. If a gate fails, diagnose and fix — or
kill it. Don't grind.

## Architecture

```
agent/
├── config.py              # pydantic-settings singleton — import `settings`, never read os.environ
├── logging.py             # structlog setup
├── agent.py               # run_cycle / run_loop — the main loop
├── __main__.py            # click CLI (installed as `openclob`)
├── data/                  # market clients
│   ├── manifold.py        #   Manifold API (paper discovery + backtest history)
│   ├── polymarket_gamma.py#   Polymarket discovery + metadata (cheap)
│   ├── polymarket_clob.py #   order book depth + signed orders via py-clob-client
│   └── historical.py      #   hydrate resolved markets + snapshots for backtests
├── reasoning/             # the LLM layer
│   ├── claude_client.py   #   Bedrock wrapper with per-decision + per-day USD caps
│   ├── search.py          #   Tavily, date-bounded queries
│   ├── prompts.py         #   ambiguity check, entry reasoning, exit reasoning
│   └── temporal_guard.py  #   rejects search results published after the reasoning cutoff
├── strategy/
│   ├── filters.py         #   liquidity / category / price / blocklist pre-filter (cheap)
│   ├── entry.py           #   LLM-driven entry plan
│   ├── exit.py            #   LLM-driven exit decisions on open positions
│   ├── sizing.py          #   calibration-adjusted fractional Kelly with hard caps
│   └── calibration.py     #   per-category Brier/ECE → multiplier on bet size
├── execution/
│   ├── paper.py           #   ManifoldExecutor
│   ├── live.py            #   LiveExecutor (Polymarket; also handles dryrun)
│   └── safety.py          #   circuit breakers — NOT bypassable by the LLM
├── backtest/
│   ├── harness.py         #   replays cached snapshots
│   ├── leakage_check.py   #   Phase-1 temporal-leakage gate
│   └── metrics.py         #   Brier / ECE / ROI
├── monitor/
│   ├── positions.py       #   re-evaluate open positions each cycle
│   ├── report.py          #   daily report numbers (same metrics the gates check)
│   └── alerts.py          #   webhook alerts
└── store/
    ├── schema.sql         #   source of truth for the SQLite schema
    └── db.py              #   thin DAO; all persistence goes through db.connect()
```

### Discovery cost-shaping

Polymarket discovery is two-staged on purpose: a cheap Gamma list → `filters.passes_all` → only
survivors get an (expensive) CLOB book-depth fetch. Preserve this ordering when adding filters;
an expensive check before the pre-filter inflates per-cycle API cost linearly with market count.

### Data model

SQLite, schema in `agent/store/schema.sql`. Key tables: `markets` (everything seen, with snapshot
prices and resolution status), `decisions` (every reasoning call — prompt, search used, output,
tokens, cost; append-only), `positions` (open/closed, linked to the opening/closing decision),
`orders` (pending maker orders, tracked so stale ones can be cancelled), `metrics` (rolling
per-category Brier/ECE/PnL/calibration), `llm_usage` (daily token-cost ledger), `breaker_state`,
`market_snapshots` (backtest replay data), and `blocklist`.

### Safety invariants

- Circuit breakers in `execution/safety.py` are **not bypassable by the LLM** — new limits go
  here, not in prompts. They cover: daily loss cap (halt 24h), max open positions, per-market
  cap, slippage guard (cancel if executed vs. quoted differs > 2%), API-failure cooldown
  (3 consecutive failures → halt 1h), and a manual trip.
- Decisions and outcomes are logged to SQLite so calibration can recompute — don't add ephemeral
  state that bypasses the DB.
- `temporal_guard` ensures backtests only use information available before a market's cutoff. Any
  new search/data path must go through it or document why it can't leak. The `leakage-check`
  command validates that this actually works.

## Configuration

All config is environment-driven via `.env` (see [`.env.example`](./.env.example) for the full,
documented list). Highlights:

- **Runtime** — `AGENT_MODE`, `AGENT_BANKROLL`, `AGENT_CYCLE_SECONDS`, `AGENT_CATEGORIES`,
  `AGENT_PER_MARKET_CAP`, `AGENT_MAX_POSITIONS`, `AGENT_DAILY_LOSS_CAP`.
- **LLM (AWS Bedrock)** — `AWS_*` credentials, `BEDROCK_MODEL_ID`, `BEDROCK_MODEL_ID_CHEAP`
  (used for the cheap ambiguity pre-filter), `LLM_PER_DECISION_USD_CAP`, `LLM_PER_DAY_USD_CAP`,
  and the per-MTok pricing used for budget accounting.
- **Search** — `TAVILY_API_KEY`, `TAVILY_MAX_RESULTS`.
- **Venues** — `MANIFOLD_*` (paper); `POLYMARKET_*` + `POLYGON_RPC_URL` (live/dryrun).
- **Storage / observability** — `AGENT_DB_PATH`, `AGENT_LOG_PATH`, `AGENT_LOG_LEVEL`,
  `ALERT_WEBHOOK_URL`.

## Development

```bash
pytest                              # full suite
pytest tests/test_safety.py -q      # single file
pytest tests/test_safety.py::test_name
ruff check . && ruff format .
mypy agent
```

Requires Python ≥ 3.11.
</content>
</invoke>
