"""Temporal-leakage check (PRD §8.5).

Run the backtest twice:
  - clean: as_of = resolution - sample_days
  - leaky: as_of = resolution + 1 day (search can see post-resolution coverage)

If the clean Brier is NOT dramatically better than the leaky Brier (delta > 0.05), the
leak-prevention itself is broken and we cannot trust the clean numbers.

This is the single most common way LLM forecasting benchmarks lie to themselves.
"""

from __future__ import annotations

from typing import Any

from agent.backtest.harness import run_backtest
from agent.logging import get_logger

log = get_logger(__name__)

LEAK_DELTA_THRESHOLD = 0.05  # leaky Brier should be at least this much LOWER than clean


def run_leakage_check(*, sample_days: int = 7, limit: int = 100) -> dict[str, Any]:
    log.info("leakage_check.start", limit=limit)
    clean = run_backtest(sample_days=sample_days, limit=limit, leak=False)
    leaky = run_backtest(sample_days=sample_days, limit=limit, leak=True)

    clean_brier = clean.get("brier")
    leaky_brier = leaky.get("brier")

    passes = False
    delta = None
    if clean_brier is not None and leaky_brier is not None:
        delta = clean_brier - leaky_brier   # positive = leaky is better, as expected
        passes = delta >= LEAK_DELTA_THRESHOLD

    summary = {
        "clean_brier": clean_brier,
        "leaky_brier": leaky_brier,
        "delta": delta,
        "threshold": LEAK_DELTA_THRESHOLD,
        "passes": passes,
        "clean_summary": clean,
        "leaky_summary": leaky,
    }
    if not passes:
        log.error("leakage_check.failed", **{k: v for k, v in summary.items()
                                              if not isinstance(v, dict)})
    else:
        log.info("leakage_check.passed", clean_brier=clean_brier, leaky_brier=leaky_brier,
                 delta=delta)
    return summary
