"""Re-evaluate every open position each cycle and act on any exit signals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent.config import settings
from agent.logging import get_logger
from agent.store import db
from agent.strategy import exit as exit_mod

log = get_logger(__name__)


def _latest_prior_p_yes(market_id: str) -> float | None:
    with db.connect() as conn:
        return db.latest_prior_p_yes(conn, market_id)


def _refresh_market_price(market: dict[str, Any]) -> float:
    """Best-effort current YES price for the market. Falls back to last_price_yes."""
    venue = market["venue"]
    try:
        if venue == "polymarket":
            from agent.data.polymarket_clob import ClobClientWrapper
            book = ClobClientWrapper().fetch_book(market["yes_token_id"])
            return book.mid or market["last_price_yes"] or 0.5
        if venue == "manifold":
            from agent.data.manifold import ManifoldClient
            m = ManifoldClient().get_market(market["external_id"])
            return (m.probability if m and m.probability is not None
                    else market["last_price_yes"] or 0.5)
    except Exception as e:
        log.warning("monitor.refresh_price_failed", market_id=market["id"], error=str(e))
    return market["last_price_yes"] or 0.5


def reevaluate_all(executor: Any) -> int:
    """Re-evaluate every open position. Returns the number of exits actioned.

    `executor` must implement close_position(...) — either ManifoldExecutor, LiveExecutor,
    or SimulatedExecutor.
    """
    with db.connect() as conn:
        open_pos = db.open_positions(conn)
    if not open_pos:
        return 0

    actioned = 0
    as_of = datetime.now(UTC)
    for pos in open_pos:
        with db.connect() as conn:
            market = db.get_market(conn, pos["market_id"])
        if not market:
            log.warning("monitor.missing_market", pos_id=pos["id"], market_id=pos["market_id"])
            continue

        current_yes = _refresh_market_price(market)

        # short-circuit: resolved markets close immediately, no LLM call
        if market.get("resolved") and market.get("resolution_value") is not None:
            executor.close_position(
                position=pos, market=market, exit_decision_id=None, size_fraction=1.0,
            )
            actioned += 1
            continue

        plan = exit_mod.plan_exit(
            position=pos, market=market,
            current_price_yes=current_yes,
            prior_p_yes=_latest_prior_p_yes(pos["market_id"]),
            as_of=as_of,
        )

        if plan.action == "hold":
            continue
        if plan.action in ("close", "scale_out"):
            executor.close_position(
                position=pos, market=market,
                exit_decision_id=plan.decision_id,
                size_fraction=plan.size_fraction,
            )
            actioned += 1
        elif plan.action == "scale_in":
            # Treat as a fresh small entry of the same side at current price.
            try:
                extra_usd = pos["notional_in"] * plan.size_fraction
                # Hard-cap so scale-in never exceeds per-market cap above current total.
                cap = settings.agent_per_market_cap - pos["notional_in"]
                if cap > 0:
                    extra_usd = min(extra_usd, cap)
                    executor.place_entry(
                        market=market, side=pos["side"], usd_size=extra_usd,
                        target_price=current_yes if pos["side"] == "YES" else (1 - current_yes),
                        decision_id=plan.decision_id,
                    )
                    actioned += 1
            except Exception as e:
                log.warning("monitor.scale_in_failed", pos_id=pos["id"], error=str(e))

    if actioned:
        log.info("monitor.exits_actioned", count=actioned)
    return actioned
