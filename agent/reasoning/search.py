"""Tavily search client with date-bounded queries.

Tavily's `published_date` filtering is applied server-side via `start_date`/`end_date`
where available, and re-verified client-side by `temporal_guard.filter_results`. Both
because:
  - Server-side filtering can silently fail on undated content.
  - We want a single deterministic point at which leakage is enforced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent.config import settings
from agent.logging import get_logger
from agent.reasoning.temporal_guard import filter_results

log = get_logger(__name__)


@dataclass(slots=True)
class SearchHit:
    title: str
    url: str
    content: str
    published_date: str | None
    score: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "published_date": self.published_date,
            "score": self.score,
        }


class TavilyClient:
    def __init__(self, *, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.api_key = api_key or settings.tavily_api_key
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    @retry(
        reraise=True,
        retry=retry_if_exception_type((httpx.HTTPError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._client.post("https://api.tavily.com/search", json=payload)
        r.raise_for_status()
        return r.json()

    def search(
        self,
        query: str,
        *,
        as_of: datetime,
        max_results: int | None = None,
        allow_undated: bool = False,
        topic: str = "news",
    ) -> list[SearchHit]:
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY is not configured")

        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results or settings.tavily_max_results,
            "include_answer": False,
            "topic": topic,
            "end_date": as_of.date().isoformat(),
        }

        data = self._post(payload)
        raw_results = data.get("results", []) or []

        kept = filter_results(raw_results, as_of, allow_undated=allow_undated)
        hits = [
            SearchHit(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", "") or r.get("raw_content", ""),
                published_date=r.get("published_date"),
                score=r.get("score"),
            )
            for r in kept
        ]
        log.info(
            "tavily.search",
            query=query[:80],
            n_returned=len(raw_results),
            n_kept=len(hits),
            as_of=as_of.isoformat(),
        )
        return hits


_client_singleton: TavilyClient | None = None


def get_client() -> TavilyClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = TavilyClient()
    return _client_singleton
