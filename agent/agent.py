"""Main loop.

  every cycle:
    1. cancel stale orders (live only)
    2. re-evaluate every open position
    3. discover candidate markets, run filters + ambiguity + entry reasoning
    4. for each plan.action == 'enter', place order through executor
    5. update breakers; if any tripped → halt

Modes:
  - paper:    Manifold discovery + ManifoldExecutor
  - dryrun:   Polymarket discovery + LiveExecutor (dry-run path) — no orders sent
  - live:     Polymarket discovery + LiveExecutor
  - backtest: not run via this loop; use `python -m agent backtest`
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.config import settings
from agent.execution import safety
from agent.execution.live import LiveExecutor
from agent.execution.paper import ManifoldExecutor
from agent.logging import get_logger
from agent.monitor import alerts, positions
from agent.store import db
from agent.strategy import entry as entry_mod

log = get_logger(__name__)

MAX_CANDIDATES_PER_CYCLE = 20  # bound reasoning cost per cycle


def _discover_polymarket() -> list[dict[str, Any]]:
    from agent.data.polymarket_clob import ClobClientWrapper
    from agent.data.polymarket_gamma import GammaClient

    out: list[dict[str, Any]] = []
    gamma = GammaClient()
    clob: ClobClientWrapper | None = None
    try:
        for gm in gamma.iter_markets(active=True, closed=False, limit_per_page=100, max_pages=5):
            if not gm.yes_token_id:
                continue
            m = gm.to_market_dict()
            with db.connect() as conn:
                mid = db.upsert_market(conn, m)
                stored = db.get_market(conn, mid)
            if stored:
                out.append(stored)
            if len(out) >= MAX_CANDIDATES_PER_CYCLE * 3:
                break
    finally:
        gamma.close()

    # enrich top candidates with book depth (expensive — only for survivors of pre-filter)
    from agent.strategy.filters import passes_all
    survivors: list[dict[str, Any]] = []
    for m in out:
        if not passes_all(m).accepted:
            continue
        try:
            if clob is None:
                clob = ClobClientWrapper()
            book = clob.fetch_book(m["yes_token_id"])
            depth = book.depth_5c
            mid_price = book.mid or m["last_price_yes"]
            m["book_depth_5c"] = depth
            m["last_price_yes"] = mid_price
            with db.connect() as conn:
                db.upsert_market(conn, {**m, "raw": None})
        except Exception as e:
            log.warning("discover.depth_failed", market_id=m["id"], error=str(e))
        survivors.append(m)
        if len(survivors) >= MAX_CANDIDATES_PER_CYCLE:
            break
    return survivors


def _discover_manifold() -> list[dict[str, Any]]:
    from agent.data.manifold import ManifoldClient
    client = ManifoldClient()
    try:
        out: list[dict[str, Any]] = []
        for mm in client.iter_markets(limit_per_page=500, max_pages=2):
            if mm.is_resolved or mm.outcome_type not in ("BINARY", "PSEUDO_NUMERIC"):
                continue
            row = mm.to_market_dict()
            with db.connect() as conn:
                mid = db.upsert_market(conn, row)
                stored = db.get_market(conn, mid)
            if stored:
                out.append(stored)
            if len(out) >= MAX_CANDIDATES_PER_CYCLE * 3:
                break
        return out[:MAX_CANDIDATES_PER_CYCLE]
    finally:
        client.close()


def _executor():
    mode = settings.agent_mode
    if mode == "paper":
        return ManifoldExecutor()
    if mode in ("live", "dryrun"):
        return LiveExecutor()
    raise RuntimeError(f"main loop not applicable to mode={mode}")


def run_cycle() -> dict[str, Any]:
    """Run a single end-to-end cycle. Safe to call from cron."""
    started = datetime.now(UTC)
    log.info("cycle.start", mode=settings.agent_mode, at=started.isoformat())

    ok, checks = safety.all_clear()
    tripped = [c for c in checks if c.tripped]
    if tripped:
        for c in tripped:
            alerts.send("warning", f"breaker tripped: {c.name}", reason=c.reason)
        return {"halted": True, "reasons": [c.reason for c in tripped]}

    exe = _executor()

    # 1. cancel stale orders (live only)
    cancelled = 0
    if isinstance(exe, LiveExecutor):
        try:
            cancelled = exe.cancel_stale_orders()
        except Exception as e:
            log.warning("cycle.cancel_failed", error=str(e))

    # 2. monitor open positions
    try:
        actioned = positions.reevaluate_all(exe)
    except Exception as e:
        safety.record_api_failure()
        log.error("cycle.monitor_failed", error=str(e))
        return {"halted": False, "error": str(e)}

    # 3. discover candidates
    try:
        if settings.agent_mode == "paper":
            candidates = _discover_manifold()
        else:
            candidates = _discover_polymarket()
        safety.record_api_success()
    except Exception as e:
        safety.record_api_failure()
        log.error("cycle.discovery_failed", error=str(e))
        return {"halted": False, "actioned_exits": actioned, "error": str(e)}

    # filter out markets we already hold
    with db.connect() as conn:
        held = {p["market_id"] for p in db.open_positions(conn)}
    candidates = [c for c in candidates if c["id"] not in held]
    log.info("cycle.candidates", n=len(candidates))

    # 4. entries
    n_entered = 0
    n_skipped = 0
    for m in candidates:
        with db.connect() as conn:
            if db.in_blocklist(conn, m["question"]):
                n_skipped += 1
                continue
        try:
            plan = entry_mod.plan_entry(m)
        except Exception as e:
            log.warning("cycle.plan_failed", market_id=m["id"], error=str(e))
            continue
        if plan.action != "enter":
            n_skipped += 1
            continue
        # position-count breaker recheck (entries this cycle can trip it)
        ok2, _ = safety.all_clear()
        if not ok2:
            log.warning("cycle.aborting_entries_breaker_tripped")
            break
        try:
            exe.place_entry(
                market=m, side=plan.side, usd_size=plan.usd_size,
                target_price=plan.target_price, decision_id=plan.decision_id,
            )
            n_entered += 1
        except Exception as e:
            log.warning("cycle.entry_failed", market_id=m["id"], error=str(e))

    elapsed = (datetime.now(UTC) - started).total_seconds()
    log.info(
        "cycle.done",
        elapsed_s=elapsed, cancelled=cancelled, actioned_exits=actioned,
        candidates=len(candidates), entered=n_entered, skipped=n_skipped,
    )
    return {
        "halted": False, "elapsed_s": elapsed, "cancelled": cancelled,
        "actioned_exits": actioned, "candidates": len(candidates),
        "entered": n_entered, "skipped": n_skipped,
    }


def run_loop(cycle_seconds: int | None = None) -> None:
    import time
    period = cycle_seconds or settings.agent_cycle_seconds
    log.info("loop.start", period_seconds=period, mode=settings.agent_mode)
    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log.info("loop.interrupted")
            return
        except Exception as e:
            log.exception("loop.cycle_crashed", error=str(e))
        time.sleep(period)
