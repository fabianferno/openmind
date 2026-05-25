"""Seed demo markets: run the real analyze pipeline and capture each event stream.

Captured streams (with their real, already-mined Arc tx links) are saved under data/seeds/
so the frontend "replay" mode can play a deterministic, reliable take for the video while
the "run live" button still does a genuine cycle.

Usage:
    python -m tools.seed_demo                      # auto-pick top open markets
    python -m tools.seed_demo manifold:abc manifold:def
"""

from __future__ import annotations

import sys

from agent.api import seeds
from agent.api.analyze import run_analysis
from agent.store import db


def pick_markets(limit: int = 3) -> list[dict]:
    with db.connect() as conn:
        return db.list_tradeable_markets(conn, limit)


def seed_one(market: dict) -> None:
    events: list[dict] = []
    print(f"\n=== seeding {market['id']} — {market['question'][:60]} ===")

    def emit(event: str, data: dict) -> None:
        events.append({"event": event, "data": data})
        if event in ("ontology_generated", "graph_complete", "decision", "anchored", "settled"):
            print(f"  · {event}")

    result = run_analysis(market, emit=emit)
    path = seeds.save_seed(market["id"], events)
    print(f"  → {len(events)} events saved to {path}")
    print(f"  → action={result.get('action')} anchor={result.get('anchor_tx', '')[:14]}…")


def main() -> None:
    ids = sys.argv[1:]
    if ids:
        markets = []
        with db.connect() as conn:
            for mid in ids:
                m = db.get_market(conn, mid)
                if m:
                    markets.append(m)
                else:
                    print(f"skip unknown market {mid}")
    else:
        markets = pick_markets()

    if not markets:
        print("no markets to seed — run `POST /api/discover` first")
        return
    for m in markets:
        try:
            seed_one(m)
        except Exception as e:  # noqa: BLE001
            print(f"  ! failed: {e}")
    print(f"\nseeded {len(seeds.list_seeds())} market(s): {seeds.list_seeds()}")


if __name__ == "__main__":
    main()
