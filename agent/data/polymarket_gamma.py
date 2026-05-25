"""Polymarket Gamma API — market discovery and metadata.

Gamma exposes both active and resolved markets without auth. We use it for:
  - Active market discovery (live cycle).
  - Resolved-market dump (backtest harness, Phase 1).

The CLOB client is used separately for order books and order placement.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent.config import settings
from agent.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class GammaMarket:
    """Normalised Polymarket market record."""
    condition_id: str
    question: str
    category: str | None
    end_date: str | None
    closed_time: str | None
    resolved: bool
    resolution_value: float | None       # 1.0 YES / 0.0 NO / None
    yes_token_id: str | None
    no_token_id: str | None
    last_price_yes: float | None
    volume_24h: float | None
    liquidity: float | None
    resolution_source: str | None
    description: str | None
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    def to_market_dict(self) -> dict[str, Any]:
        return {
            "venue": "polymarket",
            "external_id": self.condition_id,
            "question": self.question,
            "category": (self.category or "").lower() or None,
            "resolution_source": self.resolution_source,
            "resolution_rules": self.description,
            "yes_token_id": self.yes_token_id,
            "no_token_id": self.no_token_id,
            "end_date": self.end_date,
            "closed_time": self.closed_time,
            "resolved": self.resolved,
            "resolution_value": self.resolution_value,
            "last_price_yes": self.last_price_yes,
            "volume_24h": self.volume_24h,
            "book_depth_5c": None,           # filled by CLOB client
            "raw": self.raw,
        }


class GammaClient:
    def __init__(self, *, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base = (base_url or settings.polymarket_gamma_url).rstrip("/")
        self._client = httpx.Client(timeout=timeout, headers={"accept": "application/json"})

    def close(self) -> None:
        self._client.close()

    @retry(
        reraise=True,
        retry=retry_if_exception_type((httpx.HTTPError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = self._client.get(f"{self.base}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def iter_markets(
        self,
        *,
        active: bool | None = None,
        closed: bool | None = None,
        limit_per_page: int = 100,
        max_pages: int = 50,
        category: str | None = None,
        tag_id: int | None = None,
        category_label: str | None = None,
        order: str = "endDate",
        ascending: bool = False,
        end_date_min: str | None = None,
        end_date_max: str | None = None,
    ) -> Iterator[GammaMarket]:
        """Iterate Gamma markets.

        Polymarket's Gamma silently ignores `tag_slug` — only `tag_id` actually filters.
        Pass `tag_id` (int) to filter and `category_label` to stamp on each returned market
        (since payloads don't expose the parent tag's slug/label directly).
        """
        offset = 0
        for _ in range(max_pages):
            params: dict[str, Any] = {
                "limit": limit_per_page,
                "offset": offset,
                "order": order,
                "ascending": "true" if ascending else "false",
            }
            if active is not None:
                params["active"] = str(active).lower()
            if closed is not None:
                params["closed"] = str(closed).lower()
            if tag_id is not None:
                params["tag_id"] = tag_id
            elif category:
                # legacy: kept so existing callers don't break, but tag_slug is ignored by Gamma
                params["tag_slug"] = category
            if end_date_min:
                params["end_date_min"] = end_date_min
            if end_date_max:
                params["end_date_max"] = end_date_max
            data = self._get("/markets", params=params)
            if not isinstance(data, list) or not data:
                return
            for row in data:
                m = _normalise_gamma(row, category_override=category_label)
                if m:
                    yield m
            if len(data) < limit_per_page:
                return
            offset += limit_per_page

    def get_market(self, condition_id: str) -> GammaMarket | None:
        data = self._get(f"/markets/{condition_id}")
        if isinstance(data, dict):
            return _normalise_gamma(data)
        return None


def _parse_pg_timestamp(s: str | None) -> str | None:
    """Normalise Gamma timestamps to ISO-8601 UTC.

    Gamma returns two formats: ISO-Z ('2024-09-10T00:00:00Z') and a Postgres-style
    'YYYY-MM-DD HH:MM:SS+00' (no T, no Z) for closedTime. Normalise to ISO with a
    space-or-T tolerant parser, fall back to the raw string if we can't parse.
    """
    if not s:
        return None
    raw = s.strip()
    cleaned = raw.replace(" ", "T")
    if cleaned.endswith("+00"):
        cleaned = cleaned[:-3] + "+00:00"
    elif cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(cleaned).isoformat()
    except ValueError:
        return raw


def _normalise_gamma(
    row: dict[str, Any], *, category_override: str | None = None
) -> GammaMarket | None:
    """Map Gamma API fields → GammaMarket. Returns None on hopeless rows."""
    if not row.get("conditionId") and not row.get("condition_id"):
        return None
    condition_id = row.get("conditionId") or row.get("condition_id")

    tokens = row.get("tokens") or row.get("clobTokenIds")
    yes_id, no_id = None, None
    last_price_yes = None
    if isinstance(tokens, list) and tokens and isinstance(tokens[0], dict):
        for t in tokens:
            outcome = (t.get("outcome") or "").lower()
            if outcome == "yes":
                yes_id = t.get("tokenId") or t.get("token_id")
                p = t.get("price")
                last_price_yes = float(p) if p is not None else None
            elif outcome == "no":
                no_id = t.get("tokenId") or t.get("token_id")
    elif isinstance(tokens, str):
        # Some payloads ship "[\"yesId\", \"noId\"]" as a JSON string.
        try:
            arr = json.loads(tokens)
            if isinstance(arr, list) and len(arr) >= 2:
                yes_id, no_id = arr[0], arr[1]
        except json.JSONDecodeError:
            pass
    elif isinstance(tokens, list) and tokens and isinstance(tokens[0], str):
        if len(tokens) >= 2:
            yes_id, no_id = tokens[0], tokens[1]

    if last_price_yes is None and row.get("lastTradePrice") is not None:
        try:
            last_price_yes = float(row["lastTradePrice"])
        except (TypeError, ValueError):
            pass
    if last_price_yes is None and row.get("outcomePrices"):
        try:
            prices = row["outcomePrices"]
            if isinstance(prices, str):
                prices = json.loads(prices)
            if isinstance(prices, list) and prices:
                last_price_yes = float(prices[0])
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    resolved = bool(row.get("closed")) or bool(row.get("resolved"))
    resolution_value: float | None = None
    if resolved:
        # Polymarket exposes the resolution as outcomePrices = ["1", "0"] for YES.
        try:
            prices = row.get("outcomePrices")
            if isinstance(prices, str):
                prices = json.loads(prices)
            if isinstance(prices, list) and len(prices) >= 2:
                yes_p = float(prices[0])
                if yes_p in (0.0, 1.0):
                    resolution_value = yes_p
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    if category_override:
        category = category_override
    else:
        category = None
        # Real category lives on the parent tag; Gamma rows usually only expose `events`
        # whose slug is the *market* slug, not a category. We accept tags first (rare),
        # then fall back to None rather than poisoning the field with a market slug.
        tags = row.get("tags") or []
        if isinstance(tags, list) and tags:
            first = tags[0]
            if isinstance(first, dict):
                category = first.get("slug") or first.get("label")
            elif isinstance(first, str):
                category = first

    return GammaMarket(
        condition_id=condition_id,
        question=row.get("question") or row.get("title") or "(no question)",
        category=category,
        end_date=row.get("endDate") or row.get("end_date"),
        closed_time=_parse_pg_timestamp(row.get("closedTime") or row.get("closed_time")),
        resolved=resolved,
        resolution_value=resolution_value,
        yes_token_id=str(yes_id) if yes_id else None,
        no_token_id=str(no_id) if no_id else None,
        last_price_yes=last_price_yes,
        volume_24h=_safe_float(row.get("volume24hr") or row.get("volume24Hr") or row.get("volume_24hr")),
        liquidity=_safe_float(row.get("liquidity")),
        resolution_source=row.get("resolutionSource") or row.get("resolution_source"),
        description=row.get("description"),
        raw=row,
    )


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
