"""Single-market analysis orchestration.

Ties the reasoning pipeline to execution + on-chain settlement and emits ordered events:

    market → filter_passed → (ambiguity) → search_complete → ontology_generated →
    entity_extracted… → relation_extracted… → graph_complete → evidence → decision →
    [executed → settled] → anchored → complete

`emit(event, data)` is called synchronously as each stage completes; the FastAPI layer
bridges it to an SSE stream, and the seed script uses it to capture a replayable trace.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agent.config import settings
from agent.logging import get_logger
from agent.onchain import build_trace, canonical, get_arc, trace_hash
from agent.store import db
from agent.strategy import entry as entry_mod

log = get_logger(__name__)

EmitFn = Callable[[str, dict[str, Any]], None]


def venue_market_url(m: dict[str, Any]) -> str | None:
    """Public URL of the market on its venue (so users can see the placed bet)."""
    import json as _json

    raw = m.get("raw")
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except Exception:  # noqa: BLE001
            raw = None
    venue = m.get("venue")
    if venue == "manifold":
        if isinstance(raw, dict) and raw.get("url"):
            return raw["url"]
        if isinstance(raw, dict) and raw.get("creatorUsername") and raw.get("slug"):
            return f"https://manifold.markets/{raw['creatorUsername']}/{raw['slug']}"
        return None
    if venue == "polymarket":
        slug = raw.get("slug") if isinstance(raw, dict) else None
        return f"https://polymarket.com/event/{slug}" if slug else None
    return None


def _market_summary(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m.get("id"),
        "venue": m.get("venue"),
        "question": m.get("question"),
        "category": m.get("category"),
        "end_date": m.get("end_date"),
        "price_yes": m.get("last_price_yes"),
        "volume_24h": m.get("volume_24h"),
        "market_url": venue_market_url(m),
    }


def run_analysis(
    market: dict[str, Any],
    *,
    emit: EmitFn,
    execute: bool = True,
) -> dict[str, Any]:
    """Run the full analyze→decide→anchor→settle flow for one market."""
    arc = get_arc()
    emit("market", _market_summary(market))

    plan = entry_mod.plan_entry(market, relaxed=True, emit=emit)

    # No reasoning happened (cheap filter rejected it) → nothing to anchor.
    if plan.decision_id is None:
        emit("complete", {"action": "skip", "reason": plan.reason, "anchored": False})
        return {"action": "skip", "reason": plan.reason}

    side = plan.side or ("YES" if (plan.p_yes or 0.5) >= (market.get("last_price_yes") or 0.5) else "NO")
    decision = {
        "id": plan.decision_id,
        "as_of": datetime.now(UTC).isoformat(),
        "model_id": plan.model_id,
        "p_yes": plan.p_yes,
        "confidence": plan.confidence,
        "edge": plan.edge,
        "action": plan.action if plan.action == "skip" else f"enter_{side.lower()}",
        "rationale": plan.rationale,
    }

    # build + hash the canonical reasoning trace, store the exact bytes for verification
    trace = build_trace(
        market=market, decision=decision, graph=plan.graph, evidence=plan.search_results
    )
    canon = canonical(trace)
    thash = trace_hash(canon)
    with db.connect() as conn:
        db.save_trace_blob(
            conn, decision_id=plan.decision_id, market_id=market["id"],
            trace_hash=thash, canonical_json=canon,
        )

    # execution + USDC settlement only when the agent actually takes a position
    executed = None
    settled = None
    if plan.action == "enter" and execute:
        try:
            from agent.execution.paper import ManifoldExecutor

            exe = ManifoldExecutor()
            exe.place_entry(
                market=market, side=plan.side, usd_size=plan.usd_size,
                target_price=plan.target_price, decision_id=plan.decision_id,
            )
            executed = {"status": "filled", "venue": market.get("venue"),
                        "side": plan.side, "usd_size": plan.usd_size,
                        "market_url": venue_market_url(market)}
        except Exception as e:  # noqa: BLE001 — paper execution is best-effort in the demo
            log.warning("analyze.execute_failed", market_id=market["id"], error=str(e))
            executed = {"status": "simulated", "venue": market.get("venue"),
                        "side": plan.side, "usd_size": plan.usd_size, "note": str(e)[:120],
                        "market_url": venue_market_url(market)}
        emit("executed", executed)

        settled = arc.transfer_usdc(
            arc.treasury(), settings.arc_settle_usdc, decision_id=plan.decision_id
        )
        with db.connect() as conn:
            db.record_anchor(conn, {
                "decision_id": plan.decision_id, "market_id": market["id"], "kind": "settle",
                "tx_hash": settled["tx_hash"], "explorer_url": settled.get("explorer_url"),
                "usdc_amount": settings.arc_settle_usdc, "to_address": settled.get("to"),
                "mocked": settled.get("mocked"),
            })
        emit("settled", {**settled, "usdc_amount": settings.arc_settle_usdc})

    # anchor the reasoning-trace hash on Arc (always — the reasoning is the product)
    anchor = arc.anchor(thash, decision_id=plan.decision_id)
    with db.connect() as conn:
        db.record_anchor(conn, {
            "decision_id": plan.decision_id, "market_id": market["id"], "kind": "anchor",
            "trace_hash": thash, "tx_hash": anchor["tx_hash"],
            "explorer_url": anchor.get("explorer_url"), "mocked": anchor.get("mocked"),
        })
    emit("anchored", {**anchor, "trace_hash": thash})

    emit("complete", {
        "action": plan.action, "decision_id": plan.decision_id, "trace_hash": thash,
        "anchored": True, "settled": settled is not None,
    })
    return {
        "action": plan.action, "decision_id": plan.decision_id, "side": plan.side,
        "p_yes": plan.p_yes, "edge": plan.edge, "trace_hash": thash,
        "anchor_tx": anchor["tx_hash"], "settle_tx": settled["tx_hash"] if settled else None,
    }
