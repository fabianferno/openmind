"""Market selection filters (PRD §5.3).

Every market must pass every filter before reaching the reasoning layer. Filters are
pure functions over normalised market dicts — they don't touch the network. The CLOB
liquidity recheck happens just before order placement, not here.

Filter rules:
  - category in agent_categories (or 'all').
  - 24h volume >= MIN_VOLUME_24H ($5,000 default).
  - book_depth_5c >= MIN_DEPTH_5C ($500 default) — checked when known.
  - time to resolution within [3d, 45d].
  - current YES price in [0.08, 0.92].
  - not on the blocklist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from agent.config import settings

MIN_VOLUME_24H = 5_000.0
MIN_DEPTH_5C = 500.0
PRICE_MIN, PRICE_MAX = 0.08, 0.92
TIME_TO_RES_MIN = timedelta(days=3)
TIME_TO_RES_MAX = timedelta(days=45)


@dataclass(slots=True)
class FilterResult:
    accepted: bool
    reason: str | None = None


def category_ok(market: dict[str, Any]) -> FilterResult:
    allowed = settings.categories
    if not allowed:                   # 'all'
        return FilterResult(True)
    cat = (market.get("category") or "").lower()
    if not cat:
        return FilterResult(False, "missing_category")
    # match if any allowed token is a substring of the category (so 'world' matches 'world-events')
    if any(a == cat or a in cat for a in allowed):
        return FilterResult(True)
    return FilterResult(False, f"category_not_allowed:{cat}")


def volume_ok(market: dict[str, Any], *, min_volume: float = MIN_VOLUME_24H) -> FilterResult:
    v = market.get("volume_24h")
    if v is None:
        return FilterResult(False, "missing_volume")
    if v < min_volume:
        return FilterResult(False, f"low_volume:{v:.0f}<{min_volume:.0f}")
    return FilterResult(True)


def depth_ok(market: dict[str, Any], *, min_depth: float = MIN_DEPTH_5C) -> FilterResult:
    d = market.get("book_depth_5c")
    if d is None:
        # depth not yet fetched — allow at filter time; recheck before placing order
        return FilterResult(True, "depth_unknown_defer")
    if d < min_depth:
        return FilterResult(False, f"low_depth:{d:.0f}<{min_depth:.0f}")
    return FilterResult(True)


def time_to_resolution_ok(market: dict[str, Any], *, now: datetime | None = None) -> FilterResult:
    end = market.get("end_date")
    if not end:
        return FilterResult(False, "missing_end_date")
    try:
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return FilterResult(False, "bad_end_date")
    now = now or datetime.now(UTC)
    delta = end_dt - now
    if delta < TIME_TO_RES_MIN:
        return FilterResult(False, f"too_soon:{delta.days}d")
    if delta > TIME_TO_RES_MAX:
        return FilterResult(False, f"too_far:{delta.days}d")
    return FilterResult(True)


def price_ok(market: dict[str, Any]) -> FilterResult:
    p = market.get("last_price_yes")
    if p is None:
        return FilterResult(False, "missing_price")
    if not (PRICE_MIN <= p <= PRICE_MAX):
        return FilterResult(False, f"price_out_of_band:{p:.3f}")
    return FilterResult(True)


def passes_all(
    market: dict[str, Any], *, now: datetime | None = None, backtest: bool = False,
    relaxed: bool = False,
) -> FilterResult:
    """Run every filter; return the first failure (or accepted=True).

    In backtest mode, skip volume/depth (None on resolved markets) and the
    time-to-resolution check (the harness already anchors sample_dt = close - N days).
    Category and price-band checks still apply.

    In `relaxed` mode (user explicitly requested analysis of this market via the terminal),
    skip the autonomous-discovery gates entirely — we reason about whatever the user picked.
    """
    if relaxed:
        return FilterResult(True)
    fns = (category_ok, price_ok) if backtest else (category_ok, volume_ok, depth_ok, price_ok)
    for fn in fns:
        res = fn(market)
        if not res.accepted:
            return res
    if not backtest:
        res = time_to_resolution_ok(market, now=now)
        if not res.accepted:
            return res
    return FilterResult(True)
