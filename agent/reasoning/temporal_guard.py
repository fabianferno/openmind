"""Temporal guard.

Backtest integrity hinges on this. At sample-time `as_of`, the agent must NOT see
information dated > `as_of`. Three defences (§8.5 of the PRD):

1. This module — drops search hits whose `published_date` is missing or > as_of.
2. Prompt instructions — explicit "ignore content post-dating ${as_of}".
3. Leakage test — backtest/leakage_check.py runs an intentional-leak comparison.

Defence (1) is here. A hit with NO published_date is dropped by default because
"undated" is the most common leak vector in real-world search results.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.logging import get_logger

log = get_logger(__name__)


def parse_iso(s: str | None) -> datetime | None:
    """Parse a date string. Accepts ISO-8601 and RFC 2822 (Tavily news mode)."""
    if not s:
        return None
    s = s.strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    # Tavily's `topic=news` returns RFC 2822: 'Wed, 06 Nov 2024 08:26:00 +0000'
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt
    except (TypeError, ValueError):
        pass
    return None


def filter_results(
    results: list[dict[str, Any]],
    as_of: datetime,
    *,
    allow_undated: bool = False,
) -> list[dict[str, Any]]:
    """Return only results whose `published_date` is <= `as_of`.

    Args:
        results: list of dicts with at least 'published_date' (ISO string, optional).
        as_of: the agent's logical "now". Tz-aware.
        allow_undated: if True, undated results pass through. Default False — undated
            content is the main leakage vector and is dropped by default.
    """
    kept: list[dict[str, Any]] = []
    dropped = 0
    for r in results:
        pub = parse_iso(r.get("published_date"))
        if pub is None:
            if allow_undated:
                kept.append(r)
            else:
                dropped += 1
            continue
        # Normalise tz-naive published dates to UTC by assuming UTC.
        if pub.tzinfo is None:
            from datetime import UTC
            pub = pub.replace(tzinfo=UTC)
        if pub <= as_of:
            kept.append(r)
        else:
            dropped += 1
    if dropped:
        log.debug("temporal_guard.dropped", dropped=dropped, kept=len(kept), as_of=as_of.isoformat())
    return kept
