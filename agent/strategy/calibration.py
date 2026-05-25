"""Rolling Brier/ECE tracking + calibration multiplier per category.

Brier score (binary): mean of (p - y)^2 across resolved bets, where y in {0,1}.
ECE (expected calibration error): mean absolute gap between predicted probability and
empirical frequency across bins.

Multiplier rule (PRD §5.6):
  - Starts at 0.5 for every category.
  - Only raised toward 1.0 once a category has >= 30 resolved bets with Brier <= 0.18.
  - Drops back toward 0.5 if Brier degrades.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from agent.logging import get_logger
from agent.store import db

log = get_logger(__name__)

BRIER_GOOD = 0.15
BRIER_OK = 0.18
MIN_BETS_FOR_RAISE = 30


@dataclass(slots=True)
class CategoryMetrics:
    category: str
    n: int
    brier: float | None
    ece: float | None
    realized_pnl: float
    realized_roi: float | None
    calibration_mul: float


def brier_score(preds: Iterable[tuple[float, float]]) -> float | None:
    """Each pred = (p_yes, outcome_in_{0,1})."""
    pairs = list(preds)
    if not pairs:
        return None
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def ece(preds: Iterable[tuple[float, float]], *, n_bins: int = 10) -> float | None:
    pairs = list(preds)
    if not pairs:
        return None
    bins: list[list[tuple[float, float]]] = [[] for _ in range(n_bins)]
    for p, y in pairs:
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, y))
    total = len(pairs)
    acc = 0.0
    for b in bins:
        if not b:
            continue
        mean_p = sum(p for p, _ in b) / len(b)
        mean_y = sum(y for _, y in b) / len(b)
        acc += (len(b) / total) * abs(mean_p - mean_y)
    return acc


def _next_multiplier(prev: float, n: int, brier: float | None) -> float:
    if brier is None or n < MIN_BETS_FOR_RAISE:
        return prev
    if brier <= BRIER_GOOD:
        return min(1.0, prev + 0.1)
    if brier <= BRIER_OK:
        return min(1.0, prev + 0.05)
    return max(0.5, prev - 0.1)


def recompute(*, persist: bool = True) -> dict[str, CategoryMetrics]:
    """Recompute per-category and overall metrics from `decisions` + `positions`."""
    out: dict[str, CategoryMetrics] = {}
    with db.connect() as conn:
        # We score every entry decision against the eventual market resolution.
        rows = conn.execute(
            """
            SELECT d.id AS decision_id, d.p_yes, d.action, d.market_id,
                   m.category, m.resolution_value, m.resolved
              FROM decisions d
              JOIN markets m ON m.id = d.market_id
             WHERE d.kind = 'entry' AND d.p_yes IS NOT NULL
               AND m.resolved = 1 AND m.resolution_value IS NOT NULL
            """
        ).fetchall()
        per_cat: dict[str, list[tuple[float, float]]] = {}
        all_preds: list[tuple[float, float]] = []
        for r in rows:
            cat = (r["category"] or "uncategorised").lower()
            pair = (float(r["p_yes"]), float(r["resolution_value"]))
            per_cat.setdefault(cat, []).append(pair)
            all_preds.append(pair)

        pnl_rows = conn.execute(
            """
            SELECT m.category, COALESCE(SUM(p.pnl), 0) AS pnl,
                   COALESCE(SUM(p.notional_in), 0) AS notional
              FROM positions p JOIN markets m ON m.id = p.market_id
             WHERE p.status = 'closed'
             GROUP BY m.category
            """
        ).fetchall()
        pnl_by_cat = {(r["category"] or "uncategorised").lower(): (r["pnl"], r["notional"]) for r in pnl_rows}

        total_pnl = sum(p for p, _ in pnl_by_cat.values())
        total_notional = sum(n for _, n in pnl_by_cat.values())

        prev_muls = db.latest_calibration_multipliers(conn)
        as_of = datetime.now(UTC).date().isoformat()

        for cat, preds in per_cat.items():
            b = brier_score(preds)
            e = ece(preds)
            pnl, notional = pnl_by_cat.get(cat, (0.0, 0.0))
            roi = (pnl / notional) if notional > 0 else None
            mul = _next_multiplier(prev_muls.get(cat, 0.5), len(preds), b)
            metric = CategoryMetrics(cat, len(preds), b, e, pnl, roi, mul)
            out[cat] = metric
            if persist:
                db.upsert_metrics(conn, {
                    "as_of": as_of, "category": cat, "n_resolved": len(preds),
                    "brier": b, "ece": e, "realized_pnl": pnl, "realized_roi": roi,
                    "calibration_mul": mul,
                })

        overall = CategoryMetrics(
            "overall",
            len(all_preds),
            brier_score(all_preds),
            ece(all_preds),
            total_pnl,
            (total_pnl / total_notional) if total_notional > 0 else None,
            sum(m.calibration_mul for m in out.values()) / max(1, len(out)),
        )
        out["overall"] = overall
        if persist:
            db.upsert_metrics(conn, {
                "as_of": as_of, "category": "overall", "n_resolved": overall.n,
                "brier": overall.brier, "ece": overall.ece,
                "realized_pnl": overall.realized_pnl, "realized_roi": overall.realized_roi,
                "calibration_mul": overall.calibration_mul,
            })

    log.info("calibration.recomputed", n_categories=len(out))
    return out


def multiplier_for(category: str | None) -> float:
    """Lookup the latest multiplier for a category, defaulting to 0.5."""
    if not category:
        return 0.5
    with db.connect() as conn:
        muls = db.latest_calibration_multipliers(conn)
    return muls.get(category.lower(), 0.5)
