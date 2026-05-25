"""Polymarket CLOB client — order books, order construction, order placement.

Wraps `py-clob-client`. We deliberately keep the surface narrow:

  - `book_depth_5c(token_id)` → notional liquidity within 5¢ of mid (used by filters).
  - `mid_price(token_id)` → best-bid/ask midpoint, or None.
  - `place_limit_order(...)` / `place_market_order(...)` — return a CLOB order id.
  - `cancel_order(order_id)`.

`py-clob-client` is required at runtime; we import lazily so the rest of the project can
be imported without it during paper/backtest phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.config import settings
from agent.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class BookSummary:
    token_id: str
    best_bid: float | None
    best_ask: float | None
    mid: float | None
    bid_depth_5c: float            # notional USD bid liquidity within 5¢ of mid
    ask_depth_5c: float            # notional USD ask liquidity within 5¢ of mid

    @property
    def depth_5c(self) -> float:
        return min(self.bid_depth_5c, self.ask_depth_5c)


def _import_clob() -> tuple[Any, Any, Any, Any]:
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds, OrderArgs
        from py_clob_client.order_builder.constants import BUY, SELL
    except ImportError as e:
        raise RuntimeError(
            "py-clob-client is required for live/dryrun mode. pip install py-clob-client"
        ) from e
    return ClobClient, ApiCreds, OrderArgs, (BUY, SELL)


class ClobClientWrapper:
    """Thin wrapper. Constructed lazily so non-live modes never need a private key."""

    def __init__(self) -> None:
        if not settings.polymarket_private_key:
            raise RuntimeError("POLYMARKET_PRIVATE_KEY required for CLOB operations")
        ClobClient, ApiCreds, _OrderArgs, _sides = _import_clob()

        client = ClobClient(
            host=settings.polymarket_clob_url,
            key=settings.polymarket_private_key,
            chain_id=settings.polymarket_chain_id,
            signature_type=settings.polymarket_sig_type,
            funder=settings.polymarket_funder_address,
        )

        try:
            creds = client.create_or_derive_api_creds()
            client.set_api_creds(creds)
        except Exception as e:
            log.warning("clob.api_creds_setup_failed", error=str(e))

        self._client = client
        self._BUY, self._SELL = _sides
        self._OrderArgs = _OrderArgs

    # ---- book ----

    def fetch_book(self, token_id: str) -> BookSummary:
        book = self._client.get_order_book(token_id)
        bids = list(book.bids or [])
        asks = list(book.asks or [])

        best_bid = float(bids[-1].price) if bids else None
        best_ask = float(asks[0].price) if asks else None
        mid = (
            (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None
        )

        def depth(side_levels: list[Any], ref: float | None) -> float:
            if ref is None:
                return 0.0
            total = 0.0
            for lvl in side_levels:
                price = float(lvl.price)
                size = float(lvl.size)
                if abs(price - ref) <= 0.05:
                    total += price * size
            return total

        return BookSummary(
            token_id=token_id,
            best_bid=best_bid,
            best_ask=best_ask,
            mid=mid,
            bid_depth_5c=depth(bids, mid),
            ask_depth_5c=depth(asks, mid),
        )

    # ---- orders ----

    def place_limit(
        self,
        *,
        token_id: str,
        side: str,           # 'YES' or 'NO' — we always BUY the token directly
        price: float,
        size: float,
        is_buy: bool = True,
    ) -> dict[str, Any]:
        order_side = self._BUY if is_buy else self._SELL
        args = self._OrderArgs(price=price, size=size, side=order_side, token_id=token_id)
        signed = self._client.create_order(args)
        resp = self._client.post_order(signed, "GTC")
        log.info("clob.placed", side=side, price=price, size=size, token=token_id[:12], resp=resp)
        return resp

    def place_taker(
        self,
        *,
        token_id: str,
        side: str,
        price: float,
        size: float,
        is_buy: bool = True,
    ) -> dict[str, Any]:
        order_side = self._BUY if is_buy else self._SELL
        args = self._OrderArgs(price=price, size=size, side=order_side, token_id=token_id)
        signed = self._client.create_order(args)
        resp = self._client.post_order(signed, "FOK")
        log.info("clob.taker", side=side, price=price, size=size, token=token_id[:12], resp=resp)
        return resp

    def cancel(self, order_id: str) -> Any:
        return self._client.cancel(order_id=order_id)

    def get_balance(self) -> float | None:
        try:
            bal = self._client.get_balance_allowance()
            return float(bal.get("balance", 0)) / 1e6  # USDC has 6 decimals
        except Exception as e:
            log.warning("clob.balance_failed", error=str(e))
            return None
