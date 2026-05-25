"""Live execution against Polymarket CLOB.

Maker-first (PRD §5.5): place limit orders 1-3¢ inside the spread. Taker only for
stop-loss exits and high-conviction news entries (caller passes `force_taker=True`).

Orders are persisted to the `orders` table the moment they're submitted, so a crash
between submission and DB write is recoverable on the next cycle (we'll either find the
order open at the venue or cancelled).

Dry-run mode (`AGENT_MODE=dryrun`) builds and signs orders but does NOT submit. Used to
validate signing without risking funds.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from agent.config import settings
from agent.data.polymarket_clob import ClobClientWrapper
from agent.logging import get_logger
from agent.store import db

log = get_logger(__name__)

ORDER_TTL = timedelta(hours=4)


class LiveExecutor:
    def __init__(self) -> None:
        self._clob: ClobClientWrapper | None = None

    @property
    def clob(self) -> ClobClientWrapper:
        if self._clob is None:
            self._clob = ClobClientWrapper()
        return self._clob

    def _token_id(self, market: dict[str, Any], side: str) -> str:
        token = market["yes_token_id"] if side == "YES" else market["no_token_id"]
        if not token:
            raise RuntimeError(f"market {market['id']} missing {side} token id")
        return str(token)

    # ---- entry ----

    def place_entry(
        self,
        *,
        market: dict[str, Any],
        side: str,
        usd_size: float,
        target_price: float,
        decision_id: int | None,
        force_taker: bool = False,
    ) -> dict[str, Any]:
        token = self._token_id(market, side)
        size_shares = usd_size / max(1e-6, target_price)
        dryrun = settings.agent_mode == "dryrun"

        with db.connect() as conn:
            order_id = db.record_order(conn, {
                "market_id": market["id"], "venue": "polymarket",
                "venue_order_id": None, "side": side,
                "order_type": "taker" if force_taker else "maker",
                "limit_price": target_price, "requested_size": size_shares,
                "status": "open", "decision_id": decision_id,
                "expires_at": (datetime.now(UTC) + ORDER_TTL).isoformat(),
            })

        if dryrun:
            log.info("live.dryrun.skip", market_id=market["id"], side=side,
                     price=target_price, size=size_shares)
            with db.connect() as conn:
                db.update_order(conn, order_id, status="cancelled",
                                closed_at=datetime.now(UTC).isoformat())
            return {"order_db_id": order_id, "venue_order_id": None, "dryrun": True}

        if force_taker:
            resp = self.clob.place_taker(token_id=token, side=side, price=target_price,
                                         size=size_shares, is_buy=True)
        else:
            resp = self.clob.place_limit(token_id=token, side=side, price=target_price,
                                         size=size_shares, is_buy=True)

        venue_order_id = str(resp.get("orderID") or resp.get("orderId") or resp.get("id") or "")
        status = "open"
        if (resp.get("status") or "").lower() in ("matched", "filled"):
            status = "filled"
        with db.connect() as conn:
            db.update_order(conn, order_id, venue_order_id=venue_order_id, status=status)
            if status == "filled":
                shares_filled = float(resp.get("size_matched") or size_shares)
                fill_price = float(resp.get("price") or target_price)
                db.open_position(conn, {
                    "market_id": market["id"], "venue": "polymarket",
                    "side": side, "shares": shares_filled, "entry_price": fill_price,
                    "notional_in": shares_filled * fill_price,
                    "entry_decision_id": decision_id,
                    "venue_entry_order": venue_order_id,
                    "p_yes_at_entry": fill_price if side == "YES" else (1 - fill_price),
                })
        return {"order_db_id": order_id, "venue_order_id": venue_order_id, "status": status}

    # ---- exit ----

    def close_position(
        self,
        *,
        position: dict[str, Any],
        market: dict[str, Any],
        exit_decision_id: int | None,
        size_fraction: float = 1.0,
        force_taker: bool = True,                # exits are usually time-critical
    ) -> dict[str, Any]:
        token = self._token_id(market, position["side"])
        shares = position["shares"] * size_fraction
        # For exits we SELL our shares back into the book; target_price is the limit floor.
        # Use current YES price (or 1-p for NO) as the target.
        current = float(market.get("last_price_yes") or position["entry_price"])
        target_price = current if position["side"] == "YES" else (1 - current)
        target_price = max(0.01, min(0.99, target_price))

        dryrun = settings.agent_mode == "dryrun"
        if dryrun:
            log.info("live.dryrun.exit_skip", pos_id=position["id"])
            return {"dryrun": True}

        place = self.clob.place_taker if force_taker else self.clob.place_limit
        resp = place(token_id=token, side=position["side"], price=target_price,
                     size=shares, is_buy=False)

        venue_order_id = str(resp.get("orderID") or resp.get("orderId") or resp.get("id") or "")
        fill_price = float(resp.get("price") or target_price)
        proceeds = shares * fill_price
        with db.connect() as conn:
            db.close_position(
                conn, position["id"],
                exit_price=fill_price, notional_out=proceeds,
                exit_decision_id=exit_decision_id,
                venue_exit_order=venue_order_id,
                p_yes_at_exit=fill_price if position["side"] == "YES" else (1 - fill_price),
                fees=0.0,
            )
        log.info("live.exit.filled", pos_id=position["id"], price=fill_price, proceeds=proceeds)
        return {"fill_price": fill_price, "proceeds": proceeds, "venue_order_id": venue_order_id}

    # ---- maintenance ----

    def cancel_stale_orders(self) -> int:
        """Cancel any orders past their expires_at. Returns count cancelled."""
        cancelled = 0
        now_iso = datetime.now(UTC).isoformat()
        with db.connect() as conn:
            for o in db.open_orders(conn):
                if o["expires_at"] and o["expires_at"] < now_iso:
                    try:
                        if o.get("venue_order_id"):
                            self.clob.cancel(o["venue_order_id"])
                        db.update_order(conn, o["id"], status="expired",
                                        closed_at=datetime.now(UTC).isoformat())
                        cancelled += 1
                    except Exception as e:
                        log.warning("live.cancel_failed", order_id=o["id"], error=str(e))
        if cancelled:
            log.info("live.cancelled_stale", count=cancelled)
        return cancelled
