"""Daily/weekly report. Prints a rich-formatted summary; usable from CLI."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from agent.backtest.metrics import summary as metrics_summary
from agent.store import db


def build_report() -> dict[str, Any]:
    metrics = metrics_summary()
    with db.connect() as conn:
        open_positions = db.open_positions(conn)
        breakers = db.all_breakers(conn)
        today_pnl = db.positions_today_pnl(conn)
        cost = db.llm_cost_today(conn)
    return {
        "metrics": metrics,
        "open_positions": open_positions,
        "breakers": breakers,
        "today_pnl": today_pnl,
        "llm_cost_today": cost,
    }


def print_report(console: Console | None = None) -> None:
    c = console or Console()
    r = build_report()

    c.rule("[bold]openclob daily report")

    m = r["metrics"]
    gate = m["gate"]
    overall = m["overall"]

    summary_table = Table(title="Overall (vs gate)", show_lines=False)
    summary_table.add_column("metric")
    summary_table.add_column("value")
    summary_table.add_column("gate")
    summary_table.add_column("ok")

    def fmt(v: Any) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.4f}"
        return str(v)

    def ok(actual: float | None, target: float, lower_is_better: bool = True) -> str:
        if actual is None:
            return "—"
        good = actual <= target if lower_is_better else actual >= target
        return "✓" if good else "✗"

    summary_table.add_row("n_resolved", fmt(overall["n"]), str(gate["n"]),
                          ok(overall["n"], gate["n"], lower_is_better=False))
    summary_table.add_row("brier", fmt(overall["brier"]), fmt(gate["brier"]),
                          ok(overall["brier"], gate["brier"]))
    summary_table.add_row("ece", fmt(overall["ece"]), fmt(gate["ece"]),
                          ok(overall["ece"], gate["ece"]))
    summary_table.add_row("realized_pnl", fmt(overall["realized_pnl"]), ">0",
                          ok(-overall["realized_pnl"], 0, lower_is_better=True)
                          if overall["realized_pnl"] is not None else "—")
    summary_table.add_row("realized_roi", fmt(overall["realized_roi"]), ">0",
                          ok(-(overall["realized_roi"] or 0), 0, lower_is_better=True))
    c.print(summary_table)
    c.print(f"[bold]gate passes:[/] {'✓' if m['passes_gate'] else '✗'}")

    by_cat = m["by_category"]
    if by_cat:
        cat_table = Table(title="By category")
        for col in ("category", "n", "brier", "ece", "pnl", "roi", "calibration_mul"):
            cat_table.add_column(col)
        for cat, v in by_cat.items():
            cat_table.add_row(
                cat, str(v["n"]), fmt(v["brier"]), fmt(v["ece"]),
                fmt(v["pnl"]), fmt(v["roi"]), fmt(v["calibration_mul"]),
            )
        c.print(cat_table)

    if r["open_positions"]:
        pos_table = Table(title="Open positions")
        for col in ("id", "market_id", "side", "shares", "entry_price", "notional_in", "opened_at"):
            pos_table.add_column(col)
        for p in r["open_positions"]:
            pos_table.add_row(*[str(p.get(c, "")) for c in (
                "id", "market_id", "side", "shares", "entry_price", "notional_in", "opened_at"
            )])
        c.print(pos_table)
    else:
        c.print("[dim]no open positions[/]")

    if r["breakers"]:
        c.print("[bold]breakers:[/]")
        for b in r["breakers"]:
            c.print(f"  - {b['name']}: tripped={bool(b['tripped'])} reason={b.get('reason')}")

    c.print(f"[bold]today pnl:[/] {r['today_pnl']:.2f}")
    c.print(f"[bold]llm cost today:[/] ${r['llm_cost_today']:.4f}")


def report_json() -> str:
    return json.dumps(build_report(), default=str, indent=2)
