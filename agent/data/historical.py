"""Historical resolved-market dump for the Phase 1 backtest harness.

We pull resolved Polymarket markets via Gamma (filtered by `tag_id`, which is the
only category filter Gamma actually honours), and fetch price-history snapshots into
`market_snapshots`. Sample points are anchored to `closed_time` (actual close), NOT
`end_date` (scheduled), because many markets close early when the question is decided.

Markets with no usable price history are dropped — Phase 1 backtests are meaningless
on markets where the agent has no historical price to react to.

Price history endpoint (CLOB):
  GET /prices-history?market={tokenId}&interval=max&fidelity=1
  GET /prices-history?market={tokenId}&startTs=<unix>&endTs=<unix>&fidelity=60

Returns: { history: [ { t: <unix>, p: <yes_price> }, ... ] }
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent.config import settings
from agent.data.manifold import ManifoldClient
from agent.data.polymarket_gamma import GammaClient
from agent.logging import get_logger
from agent.store import db

log = get_logger(__name__)

# Default tag_ids known to map to multi-day public-information markets (PRD §5.1).
# Discovered by probing Gamma. Keep this list short and well-justified — adding broad
# tags pulls in sports/crypto-launch markets that aren't where LLM edge lives.
DEFAULT_TAG_IDS: tuple[tuple[int, str], ...] = (
    (2, "politics"),
)

# Manifold topic slugs that map to PRD-aligned categories. Order matters: we hydrate
# top-down and stamp the first matching slug as the market's category.
DEFAULT_MANIFOLD_TOPICS: tuple[str, ...] = (
    "us-politics",
    "politics-default",
    "geopolitics",
    "world-default",
)


@retry(
    reraise=True,
    retry=retry_if_exception_type((httpx.HTTPError,)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
def fetch_price_history(
    token_id: str,
    *,
    interval: str = "max",
    start_ts: int | None = None,
    end_ts: int | None = None,
    fidelity: int = 1,
) -> list[dict[str, Any]]:
    """Return list of {t: unix-seconds, p: yes_price}.

    Pass either `interval` (e.g. 'max') OR both `start_ts`/`end_ts` to query an
    explicit window. The CLOB endpoint accepts at most one of these shapes per call.
    """
    base = settings.polymarket_clob_url.rstrip("/")
    params: dict[str, Any] = {"market": token_id, "fidelity": fidelity}
    if start_ts is not None and end_ts is not None:
        params["startTs"] = start_ts
        params["endTs"] = end_ts
    else:
        params["interval"] = interval
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{base}/prices-history", params=params)
        if r.status_code == 400:
            return []
        r.raise_for_status()
        data = r.json()
    return list(data.get("history") or [])


def _resolution_dt(gm) -> datetime | None:  # GammaMarket
    """Pick the timestamp the backtest should anchor sampling to.

    Prefer closed_time (actual close); fall back to end_date when missing.
    """
    raw = gm.closed_time or gm.end_date
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def hydrate_resolved_markets(
    *,
    target: int = 500,
    categories: list[str] | None = None,         # kept for CLI back-compat; ignored
    tag_ids: list[tuple[int, str]] | None = None,
    snapshot_intervals: tuple[int, ...] = (3, 7, 14, 30),
    require_history: bool = True,
    end_date_min: str | None = None,             # ISO date, e.g. '2024-01-01'
    end_date_max: str | None = None,             # ISO date, e.g. '2025-12-31'
    ascending: bool = False,
) -> int:
    """Backfill resolved markets and their price snapshots into SQLite.

    Args:
        target: stop once we've stored at least this many resolved markets.
        tag_ids: list of (tag_id, label) pairs. Defaults to politics.
        snapshot_intervals: "days before close" sample points to record.
        require_history: if True, drop markets where prices-history returns no points.

    Returns the number of resolved markets newly stored or refreshed.
    """
    del categories  # back-compat, unused
    tags = list(tag_ids or DEFAULT_TAG_IDS)

    gamma = GammaClient()
    stored = 0
    skipped_no_history = 0
    skipped_date = 0
    try:
        for tid, label in tags:
            log.info("history.tag.start", tag_id=tid, label=label)
            for gm in gamma.iter_markets(
                active=None, closed=True,
                limit_per_page=100, max_pages=200,
                tag_id=tid, category_label=label,
                ascending=ascending,
                end_date_min=end_date_min,
                end_date_max=end_date_max,
            ):
                if stored >= target:
                    break
                if not gm.resolved or gm.resolution_value is None:
                    continue
                if not gm.yes_token_id:
                    continue

                res_dt = _resolution_dt(gm)
                if not res_dt:
                    continue

                # Date window filter
                iso_date = res_dt.date().isoformat()
                if end_date_min and iso_date < end_date_min:
                    skipped_date += 1
                    continue
                if end_date_max and iso_date > end_date_max:
                    skipped_date += 1
                    continue

                # Pull history scoped to a window around resolution. `interval=max`
                # returns whatever Polymarket considers the full series for the token;
                # if that's empty, try an explicit 90-day window pre-close.
                history = _fetch_history_for(gm.yes_token_id, res_dt)
                if not history and require_history:
                    skipped_no_history += 1
                    continue

                with db.connect() as conn:
                    market_id = db.upsert_market(conn, gm.to_market_dict())

                if history:
                    _record_snapshots(market_id, history, res_dt, snapshot_intervals)

                stored += 1
                if stored % 25 == 0:
                    log.info("history.progress", stored=stored,
                             skipped_no_history=skipped_no_history, skipped_date=skipped_date)
            if stored >= target:
                break
    finally:
        gamma.close()

    log.info("history.done", stored=stored,
             skipped_no_history=skipped_no_history, skipped_date=skipped_date)
    return stored


def _fetch_history_for(token_id: str, res_dt: datetime) -> list[dict[str, Any]]:
    try:
        h = fetch_price_history(token_id, interval="max", fidelity=1)
        if h:
            return h
    except httpx.HTTPError as e:
        log.warning("history.max_failed", token=token_id, error=str(e))
    try:
        start_ts = int((res_dt - timedelta(days=90)).timestamp())
        end_ts = int(res_dt.timestamp())
        return fetch_price_history(token_id, start_ts=start_ts, end_ts=end_ts, fidelity=60)
    except httpx.HTTPError as e:
        log.warning("history.window_failed", token=token_id, error=str(e))
        return []


def hydrate_manifold_resolved_markets(
    *,
    target: int = 300,
    topics: list[str] | None = None,
    snapshot_intervals: tuple[int, ...] = (3, 7, 14, 30),
    end_date_min: str | None = None,         # ISO date
    end_date_max: str | None = None,         # ISO date
    min_volume: float = 100.0,               # skip illiquid markets (Mana)
) -> int:
    """Hydrate resolved binary politics markets from Manifold.

    Manifold retains full bet history for any market, so we can derive snapshots at
    arbitrary points in the past — solving the data-availability gap that blocks the
    Polymarket Phase-1 backtest.
    """
    chosen_topics = list(topics or DEFAULT_MANIFOLD_TOPICS)
    client = ManifoldClient()
    stored = 0
    skipped_no_bets = 0
    skipped_date = 0
    skipped_low_vol = 0
    seen_ids: set[str] = set()

    try:
        for topic in chosen_topics:
            log.info("history.manifold.topic", topic=topic)
            for mm in client.search_markets(
                topic_slug=topic,
                filter_="resolved",
                sort="most-popular",
                limit_per_page=100,
                max_pages=10,
            ):
                if stored >= target:
                    break
                if mm.id in seen_ids:
                    continue
                if mm.outcome_type != "BINARY" or mm.resolution not in ("YES", "NO"):
                    continue
                if (mm.volume or 0.0) < min_volume:
                    skipped_low_vol += 1
                    continue

                # Anchor on resolutionTime; fall back to closeTime
                res_iso = mm.resolution_time or mm.end_date
                if not res_iso:
                    continue
                res_dt = datetime.fromisoformat(res_iso.replace("Z", "+00:00"))
                iso_date = res_dt.date().isoformat()
                if end_date_min and iso_date < end_date_min:
                    skipped_date += 1
                    continue
                if end_date_max and iso_date > end_date_max:
                    skipped_date += 1
                    continue

                bets = client.fetch_bets(contract_id=mm.id, limit_per_page=1000, max_pages=20)
                if not bets:
                    skipped_no_bets += 1
                    continue

                with db.connect() as conn:
                    market_id = db.upsert_market(conn, mm.to_market_dict())
                _record_snapshots_from_bets(market_id, bets, res_dt, snapshot_intervals)

                seen_ids.add(mm.id)
                stored += 1
                if stored % 25 == 0:
                    log.info("history.manifold.progress", stored=stored,
                             skipped_no_bets=skipped_no_bets,
                             skipped_low_vol=skipped_low_vol,
                             skipped_date=skipped_date)
            if stored >= target:
                break
    finally:
        client.close()

    log.info("history.manifold.done", stored=stored,
             skipped_no_bets=skipped_no_bets,
             skipped_low_vol=skipped_low_vol,
             skipped_date=skipped_date)
    return stored


def _record_snapshots_from_bets(
    market_id: str,
    bets: list[dict[str, Any]],
    res_dt: datetime,
    days_before: tuple[int, ...],
) -> None:
    """Derive snapshots from a sorted-oldest-first list of Manifold bets.

    Each bet has `probAfter` (price after the bet) and `createdTime` (ms epoch).
    For each target sample-time, record the most recent bet's probAfter at-or-before.
    """
    points: list[tuple[datetime, float]] = []
    for b in bets:
        ts = b.get("createdTime")
        prob = b.get("probAfter")
        if ts is None or prob is None:
            continue
        try:
            t_dt = datetime.fromtimestamp(int(ts) / 1000, tz=UTC)
        except (TypeError, ValueError):
            continue
        try:
            p = float(prob)
        except (TypeError, ValueError):
            continue
        points.append((t_dt, p))
    if not points:
        return
    points.sort(key=lambda x: x[0])

    with db.connect() as conn:
        for d in days_before:
            target_dt = res_dt - timedelta(days=d)
            chosen: tuple[datetime, float] | None = None
            for ts, price in points:
                if ts <= target_dt:
                    chosen = (ts, price)
                else:
                    break
            if not chosen:
                continue
            ts, price = chosen
            db.insert_snapshot(
                conn,
                {
                    "market_id": market_id,
                    "as_of": target_dt.isoformat(timespec="seconds"),
                    "price_yes": price,
                    "raw": {"sampled_ts": ts.isoformat(), "days_before": d},
                },
            )


def _record_snapshots(
    market_id: str,
    history: list[dict[str, Any]],
    res_dt: datetime,
    days_before: tuple[int, ...],
) -> None:
    """For each target sample-time, record the closest-but-not-after price."""
    points = [
        (datetime.fromtimestamp(int(h["t"]), tz=UTC), float(h["p"]))
        for h in history if "t" in h and "p" in h
    ]
    points.sort(key=lambda x: x[0])
    if not points:
        return

    with db.connect() as conn:
        for d in days_before:
            target_dt = res_dt - timedelta(days=d)
            chosen = None
            for ts, price in points:
                if ts <= target_dt:
                    chosen = (ts, price)
                else:
                    break
            if not chosen:
                continue
            ts, price = chosen
            db.insert_snapshot(
                conn,
                {
                    "market_id": market_id,
                    "as_of": target_dt.isoformat(timespec="seconds"),
                    "price_yes": price,
                    "raw": {"sampled_ts": ts.isoformat(), "days_before": d},
                },
            )
