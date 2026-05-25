"""Manifold Markets API client — used during the Phase 2 paper-trading phase.

Manifold uses play money ("Mana") on continuous AMMs. We treat it as a faithful proxy
for the buy/sell-shares model on Polymarket: place a bet at a target probability and the
AMM gives you shares at that implied price.

API docs: https://docs.manifold.markets/api
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent.config import settings
from agent.logging import get_logger

log = get_logger(__name__)


PRIORITY_GROUP_SLUGS: tuple[str, ...] = (
    "us-politics", "politics-default", "geopolitics", "world-default",
    "world-politics", "international-politics", "elections",
)


@dataclass(slots=True)
class ManifoldMarket:
    id: str
    slug: str
    question: str
    outcome_type: str
    probability: float | None
    volume: float | None              # cumulative volume (Mana)
    volume_24h: float | None
    end_date: str | None              # closeTime ISO
    resolution_time: str | None       # actual resolutionTime ISO
    is_resolved: bool
    resolution: str | None     # 'YES' / 'NO' / 'MKT' / 'CANCEL'
    resolution_probability: float | None
    description: str
    group_slugs: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def primary_category(self) -> str | None:
        """First group slug that overlaps PRIORITY_GROUP_SLUGS, else first group, else None."""
        for s in self.group_slugs:
            if s in PRIORITY_GROUP_SLUGS:
                return s
        return self.group_slugs[0] if self.group_slugs else None

    def to_market_dict(self) -> dict[str, Any]:
        resolution_value: float | None = None
        if self.is_resolved:
            if self.resolution == "YES":
                resolution_value = 1.0
            elif self.resolution == "NO":
                resolution_value = 0.0
            elif self.resolution == "MKT" and self.resolution_probability is not None:
                resolution_value = float(self.resolution_probability)
        return {
            "venue": "manifold",
            "external_id": self.id,
            "question": self.question,
            "category": (self.primary_category or "manifold"),
            "resolution_source": None,
            "resolution_rules": self.description,
            "yes_token_id": None,
            "no_token_id": None,
            "end_date": self.end_date,
            "closed_time": self.resolution_time or self.end_date,
            "resolved": self.is_resolved,
            "resolution_value": resolution_value,
            "last_price_yes": self.probability,
            "volume_24h": self.volume_24h,
            "book_depth_5c": None,
            "raw": self.raw,
        }


class ManifoldClient:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None,
                 timeout: float = 30.0) -> None:
        self.api_key = api_key or settings.manifold_api_key
        self.base = (base_url or settings.manifold_base_url).rstrip("/")
        headers = {"accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Key {self.api_key}"
        self._client = httpx.Client(timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    @retry(
        reraise=True,
        retry=retry_if_exception_type((httpx.HTTPError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def _req(self, method: str, path: str, **kw: Any) -> Any:
        r = self._client.request(method, f"{self.base}{path}", **kw)
        r.raise_for_status()
        if r.status_code == 204:
            return None
        return r.json()

    # ---- discovery ----

    def iter_markets(self, *, limit_per_page: int = 500, max_pages: int = 20) -> Iterator[ManifoldMarket]:
        before: str | None = None
        for _ in range(max_pages):
            params: dict[str, Any] = {"limit": limit_per_page}
            if before:
                params["before"] = before
            data = self._req("GET", "/v0/markets", params=params)
            if not isinstance(data, list) or not data:
                return
            for row in data:
                m = _normalise(row)
                if m:
                    yield m
            if len(data) < limit_per_page:
                return
            before = data[-1].get("id")

    def get_market(self, market_id: str) -> ManifoldMarket | None:
        data = self._req("GET", f"/v0/market/{market_id}")
        return _normalise(data) if data else None

    def get_market_by_slug(self, slug: str) -> ManifoldMarket | None:
        data = self._req("GET", f"/v0/slug/{slug}")
        return _normalise(data) if data else None

    def search_markets(
        self,
        *,
        term: str = "",
        filter_: str = "resolved",        # 'all' | 'open' | 'resolved' | 'closed'
        sort: str = "most-popular",
        limit_per_page: int = 100,
        max_pages: int = 20,
        topic_slug: str | None = None,    # filter by group/topic
    ) -> Iterator[ManifoldMarket]:
        """Iterate Manifold's search endpoint. Each page yields up to limit_per_page rows.

        Stamps `category` to topic_slug when provided — Manifold's search response omits
        groupSlugs, so the topic we asked for IS the right category to record.
        """
        offset = 0
        for _ in range(max_pages):
            params: dict[str, Any] = {
                "term": term,
                "filter": filter_,
                "sort": sort,
                "limit": limit_per_page,
                "offset": offset,
                "contractType": "BINARY",
            }
            if topic_slug:
                params["topicSlug"] = topic_slug
            data = self._req("GET", "/v0/search-markets", params=params)
            if not isinstance(data, list) or not data:
                return
            for row in data:
                m = _normalise(row)
                if m:
                    if topic_slug and not m.group_slugs:
                        m.group_slugs = [topic_slug]
                    yield m
            if len(data) < limit_per_page:
                return
            offset += limit_per_page

    def fetch_bets(
        self,
        *,
        contract_id: str,
        limit_per_page: int = 1000,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch ALL historical bets for a contract. Returns oldest-first.

        Manifold returns up to 1000 bets per call newest-first. We paginate via the
        `before` cursor (id of the last bet seen) until exhausted, then reverse.
        """
        out: list[dict[str, Any]] = []
        before: str | None = None
        for _ in range(max_pages):
            params: dict[str, Any] = {"contractId": contract_id, "limit": limit_per_page}
            if before:
                params["before"] = before
            page = self._req("GET", "/v0/bets", params=params)
            if not isinstance(page, list) or not page:
                break
            out.extend(page)
            if len(page) < limit_per_page:
                break
            before = page[-1].get("id") or page[-1].get("betId")
            if not before:
                break
        # Manifold returns newest-first; we want oldest-first for snapshot lookups
        out.sort(key=lambda b: b.get("createdTime") or 0)
        return out

    # ---- trading ----

    def place_bet(
        self,
        *,
        contract_id: str,
        outcome: str,                  # 'YES' or 'NO'
        amount: float,                 # Mana
        limit_prob: float | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("MANIFOLD_API_KEY required for placing bets")
        payload: dict[str, Any] = {
            "contractId": contract_id,
            "outcome": outcome,
            "amount": float(amount),
        }
        if limit_prob is not None:
            payload["limitProb"] = round(float(limit_prob), 2)
        return self._req("POST", "/v0/bet", json=payload)

    def cancel_bet(self, bet_id: str) -> None:
        self._req("POST", f"/v0/bet/cancel/{bet_id}")

    def sell_shares(
        self, *, contract_id: str, outcome: str, shares: float | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"contractId": contract_id, "outcome": outcome}
        if shares is not None:
            payload["shares"] = float(shares)
        return self._req("POST", "/v0/market/sell", json=payload)


def _normalise(row: dict[str, Any]) -> ManifoldMarket | None:
    if not row or "id" not in row:
        return None
    from datetime import UTC, datetime as _dt

    def _to_iso(ms: Any) -> str | None:
        if not ms:
            return None
        try:
            return _dt.fromtimestamp(int(ms) / 1000, tz=UTC).isoformat()
        except (TypeError, ValueError):
            return None

    return ManifoldMarket(
        id=row["id"],
        slug=row.get("slug", ""),
        question=row.get("question", ""),
        outcome_type=row.get("outcomeType", "BINARY"),
        probability=_safe_float(row.get("probability")),
        volume=_safe_float(row.get("volume")),
        volume_24h=_safe_float(row.get("volume24Hours")),
        end_date=_to_iso(row.get("closeTime")),
        resolution_time=_to_iso(row.get("resolutionTime")),
        is_resolved=bool(row.get("isResolved")),
        resolution=row.get("resolution"),
        resolution_probability=_safe_float(row.get("resolutionProbability")),
        description=row.get("textDescription") or row.get("description") or "",
        group_slugs=list(row.get("groupSlugs") or []),
        raw=row,
    )


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
