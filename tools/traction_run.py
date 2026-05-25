"""Traction batch: run the real analyze pipeline across many markets to build genuine
on-chain volume on Arc (anchored reasoning traces + USDC settlements) during the window.

Each market produces a real reasoning trace anchored on Arc; markets the agent enters also
settle USDC. Honest traction we can quantify in the report.

Usage:  python -m tools.traction_run [N]   (default 25)
"""

from __future__ import annotations

import sys
import time

from agent.agent import _discover_manifold
from agent.api.analyze import run_analysis
from agent.store import db


def gather(n: int) -> list[dict]:
    # top up the market pool, then take open, sanely-priced markets
    for _ in range(2):
        try:
            _discover_manifold()
        except Exception as e:  # noqa: BLE001
            print(f"discover warn: {e}")
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM markets
             WHERE resolved = 0 AND last_price_yes BETWEEN 0.05 AND 0.95
             ORDER BY COALESCE(volume_24h, 0) DESC
             LIMIT ?
            """,
            (n,),
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    markets = gather(n)
    print(f"analyzing {len(markets)} markets…\n")

    anchors = settles = real = mock = enters = 0
    usdc = 0.0
    for i, m in enumerate(markets, 1):
        try:
            res = run_analysis(m, emit=lambda *_: None)
        except Exception as e:  # noqa: BLE001
            print(f"[{i:>2}] FAIL {m['id']}: {str(e)[:80]}")
            continue
        with db.connect() as conn:
            recs = db.anchors_for_decision(conn, res.get("decision_id") or -1)
        for a in recs:
            if a["kind"] == "anchor":
                anchors += 1
            if a["kind"] == "settle":
                settles += 1
                usdc += a["usdc_amount"] or 0
            real += 0 if a["mocked"] else 1
            mock += 1 if a["mocked"] else 0
        if res.get("action") == "enter":
            enters += 1
        print(
            f"[{i:>2}] {res.get('action','?'):>5} "
            f"p={res.get('p_yes')} edge={res.get('edge')} "
            f"anchor={(res.get('anchor_tx') or '')[:12]}… "
            f"{(m['question'] or '')[:48]}"
        )
        time.sleep(1.0)

    print("\n=== traction summary ===")
    print(f"markets analyzed : {len(markets)}")
    print(f"entered (traded) : {enters}")
    print(f"anchors on Arc   : {anchors}")
    print(f"USDC settlements : {settles}  (~{usdc:.2f} USDC)")
    print(f"REAL on-chain tx : {real}   mock: {mock}")
    with db.connect() as conn:
        print(f"LLM cost today   : ${db.llm_cost_today(conn):.4f}")


if __name__ == "__main__":
    main()
