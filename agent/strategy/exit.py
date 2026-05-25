"""Exit decision pipeline.

For each open position, the agent re-evaluates each cycle:

  hold        — thesis intact, do nothing
  take_profit — close (or scale out) because price converged to fair
  stop_loss   — close because thesis broke or new evidence flipped
  scale_in    — add to position because edge widened
  scale_out   — trim because conviction softened

Hard-coded fast-track exits (not LLM-mediated):
  - market resolved → close at $1 / $0
  - unrealized loss exceeds STOP_LOSS_PCT * notional_in → forced stop-loss
  - time-to-resolution < HARD_CLOSE_HOURS → close to avoid resolution risk on ambiguous markets
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from agent.logging import get_logger
from agent.reasoning import claude_client, prompts, search

log = get_logger(__name__)

STOP_LOSS_PCT = 0.50            # unrealized loss > 50% of cost → stop out
TAKE_PROFIT_AUTO_PCT = 0.80     # if price has moved >= 80% of the way to $1 (or $0) → auto-take profit
HARD_CLOSE_HOURS = 12           # close anything resolving within this window


@dataclass(slots=True)
class ExitPlan:
    action: str                          # 'hold' | 'close' | 'scale_in' | 'scale_out'
    reason: str
    position_id: int
    size_fraction: float = 1.0           # fraction of position to act on
    target_price: float | None = None
    p_yes: float | None = None
    decision_id: int | None = None
    search_results: list[dict[str, Any]] = field(default_factory=list)


def _unrealized_pnl(position: dict[str, Any], current_yes: float) -> float:
    entry = position["entry_price"]
    shares = position["shares"]
    if position["side"] == "YES":
        return (current_yes - entry) * shares
    return ((1 - current_yes) - (1 - entry)) * shares


def plan_exit(
    *,
    position: dict[str, Any],
    market: dict[str, Any],
    current_price_yes: float,
    prior_p_yes: float | None,
    as_of: datetime | None = None,
) -> ExitPlan:
    as_of = as_of or datetime.now(UTC)
    pos_id = position["id"]

    # 1. resolved → close at resolution value
    if market.get("resolved") and market.get("resolution_value") is not None:
        return ExitPlan(
            action="close",
            reason=f"resolved:{market['resolution_value']}",
            position_id=pos_id,
            size_fraction=1.0,
            target_price=float(market["resolution_value"]),
        )

    # 2. hard stop-loss
    notional_in = position["notional_in"]
    unrealized = _unrealized_pnl(position, current_price_yes)
    if notional_in > 0 and unrealized <= -STOP_LOSS_PCT * notional_in:
        return ExitPlan(
            action="close",
            reason=f"hard_stop_loss:unrealized={unrealized:.2f}",
            position_id=pos_id,
            size_fraction=1.0,
            target_price=current_price_yes if position["side"] == "YES" else (1 - current_price_yes),
        )

    # 3. hard take-profit (avoid resolution risk on near-converged positions)
    side = position["side"]
    entry = position["entry_price"]
    if side == "YES":
        progress = (current_price_yes - entry) / max(1e-6, 1.0 - entry)
    else:
        progress = (entry - current_price_yes) / max(1e-6, entry)
    if progress >= TAKE_PROFIT_AUTO_PCT:
        return ExitPlan(
            action="close",
            reason=f"auto_take_profit:progress={progress:.2f}",
            position_id=pos_id,
            size_fraction=1.0,
            target_price=current_price_yes if side == "YES" else (1 - current_price_yes),
        )

    # 4. close before resolution if time-to-resolution is short
    end = market.get("end_date")
    if end:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            if end_dt - as_of <= timedelta(hours=HARD_CLOSE_HOURS):
                return ExitPlan(
                    action="close",
                    reason="near_resolution",
                    position_id=pos_id,
                    size_fraction=1.0,
                    target_price=current_price_yes if side == "YES" else (1 - current_price_yes),
                )
        except ValueError:
            pass

    # 5. LLM-mediated re-evaluation (only for positions we haven't closed yet)
    tav = search.get_client()
    hits: list[dict[str, Any]] = []
    try:
        s = tav.search(market["question"], as_of=as_of, max_results=4)
        hits.extend(h.to_dict() for h in s)
    except Exception as e:
        log.warning("exit.search_failed", market_id=market["id"], error=str(e))

    exit_prompt = prompts.build_exit_prompt(
        market,
        as_of=as_of,
        position=position,
        current_price_yes=current_price_yes,
        prior_p_yes=prior_p_yes,
        search_results=hits,
    )
    llm = claude_client.get_client()
    try:
        resp = llm.complete_json(
            system=prompts.EXIT_SYSTEM,
            user=exit_prompt,
            max_tokens=800,
            temperature=0.2,
        )
    except claude_client.BudgetExceeded as e:
        return ExitPlan("hold", f"budget:{e}", pos_id, search_results=hits)

    parsed = prompts.validate_exit(resp.parsed)
    from agent.store import db as _db
    with _db.connect() as conn:
        decision_id = _db.record_decision(conn, {
            "market_id": market["id"],
            "kind": "exit",
            "as_of": as_of.isoformat(),
            "prompt": exit_prompt,
            "search_used": [{"url": h.get("url"), "title": h.get("title"),
                             "published": h.get("published_date")} for h in hits],
            "model_id": resp.model_id,
            "response_raw": resp.text,
            "response_json": parsed,
            "p_yes": parsed["p_yes"] if parsed else None,
            "action": parsed["action"] if parsed else "hold",
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "cost_usd": resp.cost_usd,
        })

    if not parsed:
        return ExitPlan("hold", "exit_unparseable", pos_id, decision_id=decision_id, search_results=hits)

    action_map = {
        "hold": "hold",
        "take_profit": "close",
        "stop_loss": "close",
        "scale_in": "scale_in",
        "scale_out": "scale_out",
    }
    action = action_map[parsed["action"]]
    size_fraction = parsed["size_fraction"] if action != "hold" else 0.0
    target_price = current_price_yes if side == "YES" else (1 - current_price_yes)

    return ExitPlan(
        action=action,
        reason=f"llm:{parsed['action']}",
        position_id=pos_id,
        size_fraction=size_fraction,
        target_price=target_price,
        p_yes=parsed["p_yes"],
        decision_id=decision_id,
        search_results=hits,
    )
