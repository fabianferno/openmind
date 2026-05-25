"""Aggregate backtest / live metrics.

Wraps `strategy.calibration.recompute()` and produces a printable summary that maps to
the PRD §3 gate table.
"""

from __future__ import annotations

from typing import Any

from agent.config import settings
from agent.strategy import calibration

GATES = {
    "backtest": {"brier": 0.15, "ece": 0.05, "n": 300},
    "paper":    {"brier": 0.17, "ece": 0.07, "n": 100},
    "live":     {"brier": 0.17, "ece": 0.08, "n": 50},
}


def gate_for_mode(mode: str | None = None) -> dict[str, float]:
    mode = mode or settings.agent_mode
    if mode in GATES:
        return GATES[mode]
    return GATES["paper"]


def summary() -> dict[str, Any]:
    cats = calibration.recompute(persist=True)
    overall = cats.get("overall")
    gate = gate_for_mode()
    passes = bool(
        overall
        and overall.brier is not None
        and overall.ece is not None
        and overall.brier <= gate["brier"]
        and overall.ece <= gate["ece"]
        and overall.n >= gate["n"]
    )
    return {
        "mode": settings.agent_mode,
        "gate": gate,
        "overall": {
            "n": overall.n if overall else 0,
            "brier": overall.brier if overall else None,
            "ece": overall.ece if overall else None,
            "realized_pnl": overall.realized_pnl if overall else 0.0,
            "realized_roi": overall.realized_roi if overall else None,
        },
        "by_category": {
            cat: {
                "n": m.n,
                "brier": m.brier,
                "ece": m.ece,
                "pnl": m.realized_pnl,
                "roi": m.realized_roi,
                "calibration_mul": m.calibration_mul,
            }
            for cat, m in cats.items() if cat != "overall"
        },
        "passes_gate": passes,
    }
