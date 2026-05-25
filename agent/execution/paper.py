"""Paper-trading execution.

Two backends:
  - Manifold (real continuous markets, play money).
  - Simulated AMM/CLOB fills against current price snapshot (used in backtest mode).

Both expose the same `place_entry(...)` / `close_position(...)` contract used by `agent.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from agent.data.manifold import ManifoldClient
from agent.logging import get_logger
from agent.store import db

log = get_logger(__name__)


class ManifoldExecutor:
    def __init__(self) -> None:
        self._client = ManifoldClient()

    def place_entry(
        self,
        *,
        market: dict[str, Any],
        side: str,                       # 'YES' or 'NO'
        usd_size: float,
        target_price: float,
        decision_id: int | None,
    ) -> dict[str, Any]:
        # Manifold uses mana 1:1 with USD for our purposes (no fees on play money).
        # limitProb is in [0.01, 0.99] with step 0.01.
        limit = min(0.99, max(0.01, round(target_price, 2)))
        resp = self._client.place_bet(
            contract_id=market["external_id"],
            outcome=side,
            amount=usd_size,
            limit_prob=limit,
        )
        bet_id = str(resp.get("id") or resp.get("betId") or "")
        shares = float(resp.get("shares") or (usd_size / max(1e-6, limit)))
        fill_price = float(resp.get("probAfter") or limit)
        with db.connect() as conn:
            order_id = db.record_order(conn, {
                "market_id": market["id"], "venue": "manifold",
                "venue_order_id": bet_id, "side": side, "order_type": "maker",
                "limit_price": limit, "requested_size": usd_size,
                "status": "filled",
                "decision_id": decision_id,
                "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            })
            db.update_order(conn, order_id, filled_size=usd_size, closed_at=datetime.now(UTC).isoformat())
            pos_id = db.open_position(conn, {
                "market_id": market["id"], "venue": "manifold",
                "side": side, "shares": shares, "entry_price": fill_price,
                "notional_in": usd_size, "entry_decision_id": decision_id,
                "venue_entry_order": bet_id,
                "p_yes_at_entry": fill_price if side == "YES" else (1 - fill_price),
            })
        log.info("paper.entry.filled", venue="manifold", market_id=market["id"],
                 side=side, usd=usd_size, fill=fill_price, pos_id=pos_id)
        return {"position_id": pos_id, "shares": shares, "fill_price": fill_price}

    def close_position(
        self,
        *,
        position: dict[str, Any],
        market: dict[str, Any],
        exit_decision_id: int | None,
        size_fraction: float = 1.0,
    ) -> dict[str, Any]:
        shares = position["shares"] * size_fraction
        resp = self._client.sell_shares(
            contract_id=market["external_id"],
            outcome=position["side"],
            shares=shares,
        )
        proceeds = float(resp.get("amountSold") or resp.get("amount") or 0.0)
        side = position["side"]
        fill_price = proceeds / max(1e-6, shares)
        with db.connect() as conn:
            db.close_position(
                conn, position["id"],
                exit_price=fill_price,
                notional_out=proceeds,
                exit_decision_id=exit_decision_id,
                venue_exit_order=str(resp.get("id") or ""),
                p_yes_at_exit=fill_price if side == "YES" else (1 - fill_price),
                fees=0.0,
            )
        log.info("paper.exit.filled", market_id=market["id"], pos_id=position["id"],
                 fill=fill_price, proceeds=proceeds)
        return {"fill_price": fill_price, "proceeds": proceeds}


class SimulatedExecutor:
    """No-network executor used by the backtester.

    Fills always occur at the supplied current price (zero slippage, zero fees).
    Used for Phase 1 backtest only.
    """

    def place_entry(
        self,
        *,
        market: dict[str, Any],
        side: str,
        usd_size: float,
        target_price: float,
        decision_id: int | None,
    ) -> dict[str, Any]:
        fill_price = target_price
        shares = usd_size / max(1e-6, fill_price)
        with db.connect() as conn:
            pos_id = db.open_position(conn, {
                "market_id": market["id"], "venue": "simulated",
                "side": side, "shares": shares, "entry_price": fill_price,
                "notional_in": usd_size, "entry_decision_id": decision_id,
                "p_yes_at_entry": fill_price if side == "YES" else (1 - fill_price),
            })
        return {"position_id": pos_id, "shares": shares, "fill_price": fill_price}

    def close_position(
        self,
        *,
        position: dict[str, Any],
        market: dict[str, Any],
        exit_decision_id: int | None,
        size_fraction: float = 1.0,
        exit_price_override: float | None = None,
    ) -> dict[str, Any]:
        # If market is resolved, use the resolution value as exit price.
        if exit_price_override is not None:
            fill_price = exit_price_override
        elif market.get("resolved") and market.get("resolution_value") is not None:
            res = float(market["resolution_value"])
            fill_price = res if position["side"] == "YES" else (1 - res)
        else:
            fill_price = market.get("last_price_yes") or position["entry_price"]
            if position["side"] == "NO":
                fill_price = 1 - fill_price
        shares = position["shares"] * size_fraction
        proceeds = shares * fill_price
        with db.connect() as conn:
            db.close_position(
                conn, position["id"],
                exit_price=fill_price, notional_out=proceeds,
                exit_decision_id=exit_decision_id,
                venue_exit_order=None,
                p_yes_at_exit=fill_price if position["side"] == "YES" else (1 - fill_price),
                fees=0.0,
            )
        return {"fill_price": fill_price, "proceeds": proceeds}
