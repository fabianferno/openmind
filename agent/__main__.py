"""CLI entrypoint. Subcommands:

  init-db                       initialise SQLite schema
  cycle                         run a single cycle (cron-friendly)
  loop                          run forever, sleeping AGENT_CYCLE_SECONDS between cycles
  hydrate-history               pull resolved Polymarket markets + snapshots
  backtest [--days N] [--limit] run the backtest
  leakage-check [--limit N]     run the temporal-leakage check
  recompute-metrics             recompute Brier/ECE per category
  report [--json]               print the daily report
  block <pattern>               add a substring to the blocklist
"""

from __future__ import annotations

import json
import sys

import click

from agent.logging import setup_logging


@click.group()
def cli() -> None:
    """openclob — autonomous prediction-market agent."""
    setup_logging()


@cli.command("init-db")
def init_db() -> None:
    from agent.store import db
    db.init_db()
    click.echo("db: initialised")


@cli.command("cycle")
def cycle() -> None:
    from agent.agent import run_cycle
    out = run_cycle()
    click.echo(json.dumps(out, default=str, indent=2))


@cli.command("loop")
@click.option("--period", "period", type=int, default=None, help="seconds between cycles")
def loop_cmd(period: int | None) -> None:
    from agent.agent import run_loop
    run_loop(cycle_seconds=period)


@cli.command("hydrate-history")
@click.option("--source", type=click.Choice(["polymarket", "manifold"]), default="manifold",
              help="Backtest data source. Manifold has full bet history; Polymarket purges "
                   "after ~6 weeks.")
@click.option("--target", type=int, default=300, help="number of resolved markets to store")
# polymarket-specific
@click.option("--tag", "tags", multiple=True,
              help="[polymarket] tag spec 'tag_id:label' (repeatable). Default: 2:politics.")
@click.option("--allow-no-history/--require-history", default=False,
              help="[polymarket] Keep markets even if prices-history is empty. Default: drop.")
@click.option("--ascending/--descending", default=False,
              help="[polymarket] Sort direction; --ascending starts from oldest.")
# manifold-specific
@click.option("--topic", "topics", multiple=True,
              help="[manifold] topicSlug filter (repeatable). Default: us-politics, "
                   "politics-default, geopolitics, world-default.")
@click.option("--min-volume", type=float, default=100.0,
              help="[manifold] minimum cumulative Mana volume to keep a market.")
# both
@click.option("--end-date-min", default=None, help="ISO date; drop markets resolved before this.")
@click.option("--end-date-max", default=None, help="ISO date; drop markets resolved after this.")
def hydrate_history(
    source: str, target: int,
    tags: tuple[str, ...], allow_no_history: bool, ascending: bool,
    topics: tuple[str, ...], min_volume: float,
    end_date_min: str | None, end_date_max: str | None,
) -> None:
    if source == "manifold":
        from agent.data.historical import (
            DEFAULT_MANIFOLD_TOPICS,
            hydrate_manifold_resolved_markets,
        )
        n = hydrate_manifold_resolved_markets(
            target=target,
            topics=list(topics) if topics else list(DEFAULT_MANIFOLD_TOPICS),
            min_volume=min_volume,
            end_date_min=end_date_min,
            end_date_max=end_date_max,
        )
    else:
        from agent.data.historical import DEFAULT_TAG_IDS, hydrate_resolved_markets
        parsed: list[tuple[int, str]] = []
        for t in tags:
            if ":" not in t:
                raise click.BadParameter(f"--tag expects 'id:label', got {t!r}")
            tid, label = t.split(":", 1)
            parsed.append((int(tid), label.strip().lower()))
        n = hydrate_resolved_markets(
            target=target,
            tag_ids=parsed or list(DEFAULT_TAG_IDS),
            require_history=not allow_no_history,
            end_date_min=end_date_min,
            end_date_max=end_date_max,
            ascending=ascending,
        )
    click.echo(f"hydrated {n} resolved markets from {source}")


@cli.command("backtest")
@click.option("--days", "sample_days", type=int, default=7, help="N days before resolution")
@click.option("--limit", type=int, default=300, help="cap markets sampled")
@click.option("--category", "categories", multiple=True, help="category filter (repeatable)")
def backtest_cmd(sample_days: int, limit: int, categories: tuple[str, ...]) -> None:
    from agent.backtest.harness import run_backtest
    out = run_backtest(
        sample_days=sample_days, limit=limit,
        categories=list(categories) if categories else None,
    )
    click.echo(json.dumps(out, default=str, indent=2))


@cli.command("leakage-check")
@click.option("--days", "sample_days", type=int, default=7)
@click.option("--limit", type=int, default=100)
def leakage_check_cmd(sample_days: int, limit: int) -> None:
    from agent.backtest.leakage_check import run_leakage_check
    out = run_leakage_check(sample_days=sample_days, limit=limit)
    click.echo(json.dumps(
        {k: v for k, v in out.items() if not isinstance(v, dict)},
        default=str, indent=2,
    ))
    sys.exit(0 if out["passes"] else 2)


@cli.command("recompute-metrics")
def recompute() -> None:
    from agent.strategy.calibration import recompute
    out = recompute(persist=True)
    payload = {
        cat: {
            "n": m.n, "brier": m.brier, "ece": m.ece,
            "pnl": m.realized_pnl, "roi": m.realized_roi,
            "calibration_mul": m.calibration_mul,
        }
        for cat, m in out.items()
    }
    click.echo(json.dumps(payload, default=str, indent=2))


@cli.command("report")
@click.option("--json", "as_json", is_flag=True)
def report_cmd(as_json: bool) -> None:
    from agent.monitor.report import print_report, report_json
    if as_json:
        click.echo(report_json())
    else:
        print_report()


@cli.command("block")
@click.argument("pattern")
@click.option("--reason", default="")
def block_cmd(pattern: str, reason: str) -> None:
    from datetime import UTC, datetime

    from agent.store import db
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO blocklist (pattern, reason, added_at) VALUES (?, ?, ?)",
            (pattern, reason, datetime.now(UTC).isoformat()),
        )
    click.echo(f"blocked: {pattern!r}")


@cli.command("trip-breaker")
@click.argument("reason")
def trip_cmd(reason: str) -> None:
    from agent.execution.safety import trip_manual
    trip_manual(reason)
    click.echo("manual breaker tripped")


@cli.command("reset-breaker")
def reset_cmd() -> None:
    from agent.execution.safety import reset_manual
    reset_manual()
    click.echo("manual breaker reset")


if __name__ == "__main__":
    cli()
