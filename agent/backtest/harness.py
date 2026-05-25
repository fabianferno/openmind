"""Backtest harness (PRD §7 Phase 1).

For each resolved market in `markets`, pick a sample point N days before resolution,
construct a synthetic "as_of" datetime, and run the entry pipeline with date-bounded
search. Score the resulting p_yes against the actual outcome.

This module does NOT place real orders. The simulated executor records positions/PnL
against price snapshots so we can compute realised ROI alongside Brier/ECE.

A *clean* backtest run uses the temporal_guard as designed. A *leaky* run is generated
by `leakage_check.py` which flips `as_of` to a point after resolution.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from agent.execution import paper as paper_exec
from agent.logging import get_logger
from agent.store import db
from agent.strategy import entry as entry_mod

log = get_logger(__name__)


def _resolution_dt(market: dict[str, Any]) -> datetime | None:
    """Prefer actual close time over scheduled end_date.

    Many resolved markets close early when the question becomes decidable
    (e.g. an election is called). Sampling N days before scheduled end_date
    would land us after trading has already stopped — there's no price to read.
    """
    raw = market.get("closed_time") or market.get("end_date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _sample_as_of(market: dict[str, Any], days_before: int) -> datetime | None:
    res_dt = _resolution_dt(market)
    if not res_dt:
        return None
    return res_dt - timedelta(days=days_before)


def run_backtest(
    *,
    sample_days: int = 7,
    limit: int = 300,
    categories: list[str] | None = None,
    leak: bool = False,
) -> dict[str, Any]:
    """Run the backtest over the resolved markets in SQLite.

    Args:
        sample_days: N days before resolution at which the agent makes its call.
        limit: cap the number of markets sampled.
        categories: optional category filter (case-insensitive).
        leak: if True, set `as_of` to AFTER resolution. Used by leakage_check.

    Returns a summary dict with counts and metrics.
    """
    executor = paper_exec.SimulatedExecutor()
    with db.connect() as conn:
        markets = db.list_resolved_markets(conn)

    if categories:
        cats = {c.lower() for c in categories}
        markets = [m for m in markets if (m.get("category") or "").lower() in cats]

    markets = markets[:limit]
    log.info("backtest.start", n=len(markets), leak=leak, sample_days=sample_days)

    n_decisions = 0
    n_entered = 0
    n_resolved = 0
    preds: list[tuple[float, float]] = []   # (p_yes, outcome)
    pnl_total = 0.0
    notional_total = 0.0

    for m in markets:
        sample_dt = _sample_as_of(m, days_before=sample_days)
        if not sample_dt:
            continue
        if leak:
            # Move sample point to AFTER resolution → temporal guard should let everything through.
            res_dt = _resolution_dt(m)
            if not res_dt:
                continue
            sample_dt = res_dt + timedelta(days=1)

        # Use snapshot price if available, else last_price_yes.
        snap = None
        with db.connect() as conn:
            snap = db.snapshot_at_or_before(conn, m["id"], sample_dt.isoformat())
        if snap:
            m_view = {**m, "last_price_yes": snap["price_yes"]}
        else:
            m_view = m

        plan = entry_mod.plan_entry(m_view, as_of=sample_dt, backtest=True)
        n_decisions += 1

        # For metrics we need the agent's p_yes regardless of whether it entered.
        if plan.p_yes is not None:
            preds.append((plan.p_yes, float(m["resolution_value"])))
            n_resolved += 1

        if plan.action == "enter" and plan.usd_size:
            executor.place_entry(
                market=m_view, side=plan.side, usd_size=plan.usd_size,
                target_price=plan.target_price, decision_id=plan.decision_id,
            )
            n_entered += 1

            # close at resolution
            with db.connect() as conn:
                pos_dict = db.latest_open_position_for_market(conn, m["id"])
            if pos_dict:
                executor.close_position(
                    position=pos_dict, market=m, exit_decision_id=None, size_fraction=1.0,
                )

        if n_decisions % 25 == 0:
            log.info("backtest.progress", n=n_decisions, entered=n_entered)

    # tally pnl
    with db.connect() as conn:
        rows = db.simulated_closed_pnl(conn)
    for r in rows:
        pnl_total += float(r["pnl"] or 0.0)
        notional_total += float(r["notional_in"] or 0.0)

    from agent.strategy.calibration import brier_score, ece
    summary = {
        "n_markets": len(markets),
        "n_decisions": n_decisions,
        "n_entered": n_entered,
        "n_resolved": n_resolved,
        "brier": brier_score(preds),
        "ece": ece(preds),
        "pnl": pnl_total,
        "notional": notional_total,
        "roi": (pnl_total / notional_total) if notional_total else None,
        "leak": leak,
        "sample_days": sample_days,
    }
    log.info("backtest.done", **{k: v for k, v in summary.items() if v is not None})
    return summary
