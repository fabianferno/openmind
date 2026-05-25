# Prediction Market AI Agent — PRD

**Owner:** Single user (you)
**Status:** Pre-build, planning
**Last updated:** May 14, 2026

---

## 1. Overview

An autonomous Python agent that uses an LLM reasoning loop + web search to identify mispriced prediction-market contracts, take positions, manage them, and exit. The goal is to validate whether an LLM-driven forecasting pipeline can produce real, measurable edge against efficient prediction markets — and only if so, to deploy modest real capital.

The agent is built and validated in phases. Real money is the *last* step, not the first.

---

## 2. Goals & Non-Goals

### Goals

- Build a self-contained Python agent that fetches markets, reasons about them with date-bounded information, takes positions, monitors them, and exits.
- Establish via backtesting whether the reasoning pipeline beats the market baseline (Brier ≤ 0.17) on a meaningful sample.
- Run live paper trading on Manifold for skill validation before any real-money exposure.
- Graduate to Polymarket real money only if backtest and paper trading both pass explicit, pre-committed metric gates.
- Treat this as a learning system: every decision logged, every loss explained, calibration tracked continuously.

### Non-Goals

- Not a high-frequency trader. The agent operates on a 15-30 minute cycle at the fastest.
- Not a 5-minute crypto price predictor. Sub-hour BTC/ETH up/down markets are explicitly excluded — fees are highest there, LLM edge is zero there, and latency-arbitrage bots already own that space.
- Not a multi-tenant platform. Single user, single wallet, no auth layer.
- Not a payment infrastructure project. No x402, no agent-native fee rails, no on-chain identity (ERC-8004). Just a trading bot.
- Not financial advice and not designed to be reliably profitable. This is a skill-validation exercise with optional small-stakes deployment.

---

## 3. Success Metrics

The agent passes each phase only if it hits these pre-committed numbers. No "feels promising, let's continue" judgement calls.

| Metric | Backtest gate | Paper trading gate | Real money gate |
|---|---|---|---|
| Sample size (resolved markets) | ≥ 300 | ≥ 100 | Ongoing |
| Brier score | ≤ 0.15 overall | ≤ 0.17 overall | ≤ 0.17 trailing 50 |
| ECE (expected calibration error) | ≤ 0.05 | ≤ 0.07 | ≤ 0.08 trailing 50 |
| Simulated/realized ROI after fees | > 0% | > 0% | > 0% over 30 days |
| Per-category Brier (any active category) | ≤ 0.18 | ≤ 0.18 | ≤ 0.18 |
| Temporal leakage check | Passes (see §8.5) | n/a | n/a |

If any metric fails at a phase, stop. Diagnose. Either fix or kill the project. Do not "give it more time".

---

## 4. Constraints

- **Bankroll**: $20-50 at real-money phase. Treat as a learning budget that may go to zero.
- **Language**: Python only.
- **LLM**: Claude (Anthropic API) for reasoning. Cost-aware — each decision should cost <$0.05 in tokens.
- **Search**: Tavily for date-bounded web search (cheaper than Brave for agent use cases, supports `published_date` filtering needed for leakage prevention).
- **Storage**: SQLite locally. No cloud DB.
- **Scheduler**: Plain cron, 15-30 min cycle.
- **Wallet/signing**: `py-clob-client` (official Polymarket SDK) for trading, `web3.py` for any direct contract calls.
- **No external infra**: Runs on a single laptop or small VPS. No Kubernetes, no Docker complexity until/unless needed.

---

## 5. Strategy

### 5.1 Where edge comes from

The agent's edge, if any, comes from:

1. **Reasoning quality on multi-day public-information markets.** Geopolitics, politics, regulatory decisions, scheduled events. The market is slow to incorporate complex multi-source information; an LLM with structured prompts and good search can be faster on synthesis.
2. **Resolution-criterion arbitrage.** Markets where the literal wording of resolution criteria is being mispriced relative to colloquial interpretation. Reading the fine print is something LLMs do well.
3. **News-driven momentum and overshoots on hour-to-day timescales.** Major news drops, market overshoots, agent reads the news in full and fades or rides the move.

### 5.2 Where edge does not come from

- Sub-hour price prediction on liquid markets. The market price *is* the information.
- Sports markets with deep public data and specialized models. Edge here belongs to quant desks, not LLMs.
- Markets dominated by insider information (e.g., corporate events).
- Anything where the LLM is asked to predict things its training data has already memorized — this is data leakage masquerading as skill.

### 5.3 Market selection filters

Every market must pass all filters before reaching the reasoning layer:

- **Category**: geopolitics, world events, politics, technology, regulatory, scheduled-event crypto (NOT 5-minute price). Geopolitics + world events are prioritized — they're fee-free on Polymarket.
- **Liquidity**: 24h volume > $5,000 *and* order book depth > $500 within 5¢ of mid.
- **Time to resolution**: between 3 days and 45 days. Shorter than 3 days → not enough time for reasoning to pay off. Longer than 45 days → too much can change.
- **Resolution clarity**: resolution criteria pass a separate "ambiguity check" sub-prompt. Markets resolving via subjective UMA proposal language ("officially", "credibly", "by") are auto-rejected.
- **Current price**: between $0.08 and $0.92. Markets outside this range have already resolved in practice; remaining edge is in the last basis points and is dominated by noise.
- **Not in agent blocklist**: a manual blocklist of markets the operator considers off-limits (e.g., personally distressing topics, markets the operator has insider info on).

### 5.4 Trading model: buy/sell, not bet-and-hold

The agent treats YES/NO shares as continuously priced assets, not fixed-odds bets. This is a fundamental departure from the bet-once-hold-to-resolution model.

Implications:

- Every position has both an **entry decision** and an ongoing **exit decision**, re-evaluated each cycle.
- The agent can take profit before resolution (sell shares back at a higher price).
- The agent can stop out of losing positions (sell at a loss to limit downside).
- The agent can scale into and out of positions as conviction changes.
- Strategies include: mispricing capture (buy under fair value, exit when market drifts toward fair), news momentum (read news fast, take position, exit when consensus catches up), and mean reversion (fade overshoots).

### 5.5 Order placement: maker-first

The agent defaults to **limit orders inside the spread**, becoming a maker. This means:

- Zero taker fees on Polymarket.
- Eligible for maker rebates (20-25% of taker fees collected, redistributed daily) on most categories.
- Trade-off: fills are not guaranteed. The agent must handle unfilled orders, partial fills, and the case where the market moves away before the order fills.

Taker orders are used only in two situations: (a) the agent needs to exit a losing position fast (stop-loss), and (b) a high-conviction news-momentum trade where the speed of entry outweighs the fee cost.

### 5.6 Position sizing: calibration-adjusted fractional Kelly

The original doc's Kelly formula is correct but assumes you *know* the true probability. The agent doesn't — its estimate has noise that varies by category. Sizing must account for this.

```
size = bankroll × min(
    0.25 × kelly(p_agent, p_market),
    max_position_cap,
    0.05 × bankroll               # never more than 5% of bankroll on one market
) × calibration_multiplier[category]
```

`calibration_multiplier` starts at 0.5 for every category and is adjusted upward (max 1.0) only after the agent has 30+ resolved bets in that category with Brier ≤ category-specific threshold. New categories start small; proven categories get more capital.

Hard caps regardless of Kelly:
- $2 per market while paper trading
- $5 per market for first 30 days of real money
- $10 per market thereafter

---

## 6. Architecture

```
agent/
├── data/
│   ├── manifold.py            # Manifold API client (paper phase)
│   ├── polymarket_gamma.py    # Market discovery + metadata
│   ├── polymarket_clob.py     # Order book + execution via py-clob-client
│   └── historical.py          # Resolved-market dump for backtest
├── reasoning/
│   ├── claude_client.py       # Anthropic API wrapper, token accounting
│   ├── search.py              # Tavily client with date-bounded queries
│   ├── prompts.py             # Entry prompt, exit prompt, ambiguity check
│   └── temporal_guard.py      # Enforces date bounds on all search results
├── strategy/
│   ├── filters.py             # All market selection filters
│   ├── entry.py               # Entry decision logic
│   ├── exit.py                # Exit decision logic (take-profit, stop-loss, news shock)
│   ├── sizing.py              # Calibration-adjusted fractional Kelly
│   └── calibration.py         # Rolling Brier/ECE tracking per category
├── execution/
│   ├── paper.py               # Manifold execution or simulated fills
│   ├── live.py                # py-clob-client wrapper, limit-order-first
│   └── safety.py              # Daily loss cap, position cap, slippage guard
├── backtest/
│   ├── harness.py             # Replay engine over historical markets
│   ├── leakage_check.py       # Verifies search bounds are respected
│   └── metrics.py             # Brier, ECE, calibration plot, PnL curve
├── store/
│   ├── schema.sql             # SQLite schema
│   └── db.py                  # All DB I/O
├── monitor/
│   ├── positions.py           # Re-evaluate open positions each cycle
│   ├── report.py              # Daily summary, weekly metrics review
│   └── alerts.py              # Push notifications on circuit breakers, big losses
└── agent.py                   # Main loop, scheduler entrypoint
```

### 6.1 Data model (SQLite)

Four tables:

- `markets`: every market the agent has seen, with snapshot prices, metadata, resolution status.
- `decisions`: every reasoning call — input prompt, search results used, LLM output, action taken, timestamp. Append-only.
- `positions`: open and closed positions, with entry/exit prices, sizes, PnL, linked to the decision that opened/closed them.
- `metrics`: rolling Brier, ECE, PnL, calibration multiplier per category, updated daily.

### 6.2 Main loop

```
every 15-30 minutes:
    1. Re-evaluate open positions (exit.py for each)
       → may trigger sell orders
    2. Fetch new markets matching filters
    3. For each candidate market:
       - Run ambiguity check (cheap, fast prompt)
       - If passes, run full reasoning (entry.py)
       - If edge > threshold AND sizing > 0, place limit order
    4. Check unfilled orders from previous cycles; cancel stale ones
    5. Update circuit breaker state (daily PnL, position count, etc.)
    6. If any breaker tripped, halt and alert
    7. Write everything to DB
```

### 6.3 Safety / circuit breakers

These are hard-coded and not bypassable by the LLM:

- **Daily loss cap**: -20% of bankroll → halt for 24h, send alert.
- **Position cap**: max 8 open positions simultaneously.
- **Per-market cap**: max $X per market (varies by phase, see §5.6).
- **Slippage guard**: if execution price differs from quoted by >2%, cancel order.
- **API failure cooldown**: 3 consecutive API failures → halt for 1h.
- **Liquidity check**: re-verify book depth before every entry. If liquidity dropped below threshold since market was selected, skip.

---

## 7. Phased Build Plan

### Phase 0: Skeleton (days 1-3)

- Set up Python project, SQLite schema, env config.
- Stub all module interfaces (function signatures only).
- Wire up `claude_client.py` and `search.py` with smoke tests.
- **Exit criterion**: `pytest` passes; can manually invoke a search + reasoning call end-to-end.

### Phase 1: Backtest harness (week 1)

The single most important phase. Determines whether the rest of the project is worth building.

- Build `data/historical.py` to pull resolved Polymarket markets from Gamma API.
- Aim for 500+ resolved markets with full price history, spanning multiple categories.
- Build `backtest/harness.py`: for each market, pick a sample point N days before resolution, run reasoning with date-bounded search, score against actual outcome.
- Build `backtest/leakage_check.py`: rerun with intentionally broken date bounds; if results aren't dramatically better, the leak prevention is itself broken.
- Build `backtest/metrics.py`: Brier, ECE, per-category breakdown, simulated PnL after notional fees.

**Exit criterion**: Backtest gate metrics in §3 are hit on a held-out sample of 300+ markets. Temporal leakage check passes.

If the agent can't beat market baseline in backtest, **the project ends here**. No proceeding to paper trading "to see what happens".

### Phase 2: Manifold paper trading (weeks 2-6)

- Build `data/manifold.py` and `execution/paper.py`.
- Wire the live cycle to Manifold's API (free play money, real continuous markets, same mechanics).
- Run the full agent loop daily.
- Track all metrics in the same way as backtest.

**Exit criterion**: Paper trading gate metrics in §3 hit on 100+ resolved markets over at least 4 weeks. The 4 weeks matters — short runs are noise.

If paper trading metrics underperform backtest by a wide margin, that's diagnostic: either the backtest was leaky, or the live agent has a bug. Diagnose before continuing.

### Phase 3: Polymarket testnet / dry run (week 7)

- Build `data/polymarket_gamma.py`, `data/polymarket_clob.py`, `execution/live.py`.
- Connect to Polygon Amoy or run against Polymarket mainnet with order placement disabled (read-only mode).
- Validate: wallet signing works, order construction produces valid signed orders, fills are correctly parsed, position tracking matches reality.
- Replay last week of paper-trading decisions through the live execution pipeline in dry-run mode — verify it would have produced the same trades.

**Exit criterion**: Full transaction flow validated, no signing or formatting bugs.

### Phase 4: Real money, narrow scope (weeks 8-12)

- Bankroll: $20-50.
- Category restriction: **geopolitics + world events only** for the first 30 days. These are fee-free, which removes fee miscalculation from the failure modes.
- Position size hard cap: $5/market.
- Daily review of every decision and every PnL move.

**Exit criterion**: Real money gate metrics in §3 hit over 30 days.

### Phase 5: Cautious expansion (weeks 12+)

Only if Phase 4 passes:

- Slowly add fee-bearing categories where backtest showed strong edge.
- Per-category position caps raised based on calibration multiplier.
- Continue daily review for at least 60 more days before any architecture changes.

---

## 8. Specific Design Decisions

### 8.1 Reasoning prompt structure

Three distinct prompts, not one:

1. **Ambiguity check** (cheap, ~$0.005 per call): "Given this resolution criterion, is the outcome unambiguously determinable from public information by resolution date? Answer yes/no with one-sentence rationale." Filters out markets before expensive reasoning.

2. **Entry reasoning** (~$0.03-0.05): full forecasting prompt. Returns structured JSON: `{p_yes, confidence, rationale, key_signals, edge_vs_market, recommended_action}`. Required to cite specific evidence from search results.

3. **Exit reasoning** (~$0.02-0.04): re-evaluates open position. "Given current price X, your previous estimate Y, and these new signals: should we hold, take profit, stop loss, or scale in/out?"

### 8.2 Search strategy

- Date-bounded by default. The temporal guard rejects any search result published after the agent's "current time" (which equals real now in live, and the simulated sample time in backtest).
- Two-pass: first pass is a broad query for context; second pass is targeted at specific named entities or events from the first pass.
- Hard cap of 8 search queries per market entry decision. Forces focused investigation, prevents runaway costs.

### 8.3 LLM token budget

- Per-decision soft cap: $0.05.
- Per-day hard cap: $5.
- Tracked in `claude_client.py`, enforced before each call.

### 8.4 Maker order management

- Limit orders placed 1-3¢ inside the current best bid/ask, depending on conviction.
- Orders expire (auto-cancel) after 4 hours if unfilled. The market state will have changed by then; need to re-decide.
- Partial fills: position is opened at the actual filled size, not the requested size. Sizing logic must handle this gracefully.

### 8.5 Temporal leakage test (critical)

The backtest is only meaningful if the agent at sample-time T can only see information dated ≤ T. This is enforced at three levels:

1. `temporal_guard.py` filters Tavily results by `published_date`.
2. Prompts include explicit instructions to ignore any content that appears to post-date T.
3. The leakage check test: run the backtest with date bound set to *after* resolution (intentional leak). If overall Brier doesn't improve dramatically (delta > 0.05), the leak prevention is broken and the clean results are not trustworthy.

This is the single most common way LLM forecasting benchmarks lie to themselves. Build it and run it before believing any backtest number.

---

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM has no real edge on prediction markets | Medium-High | Project dies at backtest | Acceptable — the whole point of Phase 1 is to find out. Cheap to test. |
| Backtest passes due to temporal leakage | Medium | False confidence, paper trading reveals it | Leakage check (§8.5) is the safeguard. Run it every backtest run. |
| Paper trading passes due to category mix luck | Medium | Real-money loss | Per-category metrics gate. Don't graduate categories that haven't individually proven out. |
| UMA oracle resolves a market against intuition | Medium per market | -100% of stake on that market | Ambiguity filter rejects subjective-criterion markets at entry. Per-market position cap limits damage. |
| Polymarket front-end blocks the wallet | Low | Cannot place new trades, existing positions safe | Existing USDC remains in self-custody. Migrate to direct contract calls if needed. |
| API/RPC failure during open position | High frequency, low per-event impact | Stop-loss might not execute | Circuit breaker on API failures; positions are sized so unexpected hold is tolerable. |
| Model overconfidence on rare events | Medium | Big single-bet loss | Calibration multiplier starts at 0.5; hard per-market cap; Kelly is fractional. |
| Operator builds emotional attachment to the agent's "thesis" | High | Ignores stop-out signals | All exits are agent-decided. No manual override of stop-losses. Decisions logged for review, not in-the-moment intervention. |
| LLM costs exceed expected value | Low-Medium at this scale | Negative ROI even with predictive edge | Per-decision and per-day cost caps. Cheap ambiguity-check filter before expensive reasoning. |

---

## 10. Open Questions

These need answers before or during early build, not deferred:

1. **Manifold liquidity for the chosen market types**: Manifold play-money markets have different volume distributions than Polymarket. Need to verify there are enough resolving markets of relevant categories to hit 100+ in 4 weeks. If not, paper trading phase needs supplementing with simulated fills on real Polymarket prices.

2. **Tavily date-bound reliability**: Need to verify in practice that Tavily's `published_date` filter is reliably enforced and doesn't return undated or back-dated content. If unreliable, fall back to a custom URL allowlist with known-good date metadata sources.

3. **py-clob-client signature format**: Verify the client handles EIP-712 signing correctly for the agent's wallet setup, particularly if using a fresh wallet without prior on-chain history.

4. **Polygon RPC reliability**: At 15-30 min cycle, public RPC endpoints should suffice, but if order placement fails intermittently, may need a paid endpoint (Alchemy free tier is usually enough).

5. **Tax treatment of Manifold winnings**: Manifold is play money — no tax issue. But if the user later opts to participate in Manifold's prize tournaments (which can pay real money), that's a separate consideration.

---

## 11. What This PRD Does Not Cover

- Multi-agent or copy-trading features.
- Mobile interface or dashboard.
- Automated retraining or fine-tuning of any model.
- Anything beyond Polymarket + Manifold (no Kalshi, no Indian platforms, no DEX-based prediction markets).
- Tax accounting, on/off-ramp logistics, or wallet custody beyond basic single-wallet operation.

These are intentional omissions. The agent does one thing: reason about prediction markets and trade them within strict safety bounds. Scope creep is the first failure mode.

---

## 12. Decision Log

- **Platform**: Manifold (paper) → Polymarket (real). Kalshi excluded (US-only).
- **Language**: Python only. Official `py-clob-client` SDK.
- **Markets**: Multi-day public-information markets only. 5-minute crypto markets explicitly excluded.
- **Trading model**: Continuous buy/sell of shares, not bet-and-hold. Exit logic required for every position.
- **Order type**: Maker-first (limit orders), taker only for stop-losses and high-conviction news entries.
- **Sizing**: Calibration-adjusted fractional Kelly with hard per-market caps.
- **First build**: Backtest harness, including the temporal leakage check. Before anything else.

---

*This is a working PRD. Update it when reality contradicts the plan. The plan is wrong somewhere; the only question is where.*