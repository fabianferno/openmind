"""FastAPI sidecar for the openmind frontend.

Wraps the existing agent engine: streams a live analyze pipeline over SSE and serves
history (markets, decisions, graphs, traces, on-chain anchors, portfolio, metrics) from
SQLite. Run with:  uvicorn agent.api.server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from agent.api import seeds
from agent.api.analyze import run_analysis
from agent.config import settings
from agent.logging import get_logger
from agent.onchain import get_arc
from agent.store import db

log = get_logger(__name__)

app = FastAPI(title="openmind API", version="0.1.0")

# Public read-mostly API consumed by a static frontend (no cookies) → allow any origin.
# This lets the deployed Vercel app (and judges) reach the agent over SSE + REST.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# events that animate node-by-node get a small inter-event delay for a smooth build
_ANIM_DELAY = {"entity_extracted": 0.09, "relation_extracted": 0.06}


# ---------- health / config ----------

@app.get("/")
def root() -> dict[str, Any]:
    """Service banner / quick liveness check."""
    return {"service": "openmind API", "status": "ok", "docs": "/docs"}


@app.get("/health")
@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Lightweight liveness probe — no external calls (fast, for uptime/platform checks)."""
    return {"status": "ok"}


@app.get("/api/health")
def health() -> dict[str, Any]:
    arc = get_arc()
    return {
        "ok": True,
        "mode": settings.agent_mode,
        "model": settings.bedrock_model_id,
        "arc": {
            "real": arc.real,
            "chain_id": settings.arc_chain_id,
            "address": arc.address,
            "usdc_balance": arc.usdc_balance(),
            "explorer": settings.arc_explorer_base,
        },
    }


# ---------- markets ----------

@app.get("/api/markets")
def markets(limit: int = 24) -> dict[str, Any]:
    seeded = set(seeds.list_seeds())
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, venue, question, category, end_date, last_price_yes, volume_24h, resolved
              FROM markets
             WHERE resolved = 0
             ORDER BY COALESCE(volume_24h, 0) DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        d["seeded"] = any(s.startswith(d["id"].replace(":", "_")) for s in seeded)
        out.append(d)
    return {"markets": out, "seeds": list(seeded)}


@app.post("/api/discover")
def discover() -> dict[str, Any]:
    """Populate the DB with current open Manifold markets (paper-mode discovery)."""
    from agent.agent import _discover_manifold

    found = _discover_manifold()
    return {"discovered": len(found)}


# ---------- live / replay analyze (SSE) ----------

def _sse_format(event: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": event, "data": json.dumps(data)}


async def _replay_stream(events: list[dict[str, Any]]):
    for item in events:
        ev, data = item["event"], item.get("data", {})
        yield _sse_format(ev, data)
        await asyncio.sleep(_ANIM_DELAY.get(ev, 0.35))
    yield _sse_format("done", {})


async def _live_stream(market: dict[str, Any]):
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit(event: str, data: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"event": event, "data": data})

    def worker() -> None:
        try:
            run_analysis(market, emit=emit)
        except Exception as e:  # noqa: BLE001
            log.warning("analyze.worker_failed", error=str(e))
            loop.call_soon_threadsafe(
                queue.put_nowait, {"event": "error", "data": {"message": str(e)}}
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, {"event": "done", "data": {}})

    threading.Thread(target=worker, daemon=True).start()

    while True:
        item = await queue.get()
        ev, data = item["event"], item["data"]
        yield _sse_format(ev, data)
        if ev == "done":
            break
        delay = _ANIM_DELAY.get(ev)
        if delay:
            await asyncio.sleep(delay)


@app.get("/api/analyze/{market_id:path}")
async def analyze(market_id: str, replay: bool = False) -> EventSourceResponse:
    if replay:
        events = seeds.load_seed(market_id)
        if events is None:
            raise HTTPException(404, f"no seed for {market_id}")
        return EventSourceResponse(_replay_stream(events))

    with db.connect() as conn:
        market = db.get_market(conn, market_id)
    if not market:
        raise HTTPException(404, f"unknown market {market_id}")
    return EventSourceResponse(_live_stream(market))


# ---------- autonomous mode (SSE) ----------

def _pick_open_markets(n: int) -> list[dict[str, Any]]:
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


async def _auto_stream(n: int):
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def top(event: str, data: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"event": event, "data": data})

    def worker() -> None:
        try:
            markets = _pick_open_markets(n)
            top("auto_start", {"n": len(markets)})
            for idx, m in enumerate(markets):
                top("auto_pick", {
                    "index": idx,
                    "market": {"id": m["id"], "question": m["question"],
                               "category": m.get("category"), "price_yes": m.get("last_price_yes")},
                })

                def emit(ev: str, data: dict[str, Any], _i: int = idx) -> None:
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"event": "auto_event", "data": {"index": _i, "ev": ev, "data": data}},
                    )

                try:
                    run_analysis(m, emit=emit)
                except Exception as e:  # noqa: BLE001
                    top("auto_error", {"index": idx, "message": str(e)})
        except Exception as e:  # noqa: BLE001
            top("auto_error", {"index": -1, "message": str(e)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, {"event": "auto_done", "data": {}})

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = await queue.get()
        yield _sse_format(item["event"], item["data"])
        if item["event"] == "auto_done":
            break


@app.get("/api/auto")
async def auto(n: int = 3) -> EventSourceResponse:
    """Agent autonomously selects markets from its universe and trades them — no human pick."""
    return EventSourceResponse(_auto_stream(min(max(n, 1), 8)))


# ---------- history reads ----------

@app.get("/api/decisions/{decision_id}")
def decision(decision_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        d = db.get_decision(conn, decision_id)
        if not d:
            raise HTTPException(404, "unknown decision")
        if d.get("response_json"):
            d["response_json"] = json.loads(d["response_json"])
        if d.get("search_used"):
            d["search_used"] = json.loads(d["search_used"])
        graph = db.get_graph(conn, decision_id)
        anchors = db.anchors_for_decision(conn, decision_id)
        market = db.get_market(conn, d["market_id"])
    return {"decision": d, "graph": graph, "anchors": anchors,
            "market": {k: market[k] for k in ("id", "question", "category", "last_price_yes")}
            if market else None}


@app.get("/api/graph/{decision_id}")
def graph(decision_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        g = db.get_graph(conn, decision_id)
    if not g:
        raise HTTPException(404, "no graph for decision")
    return g


@app.get("/api/trace/{decision_id}")
def trace(decision_id: int) -> dict[str, Any]:
    """Return the exact canonical bytes + hash + on-chain anchors, for client-side verify."""
    with db.connect() as conn:
        blob = db.get_trace_blob(conn, decision_id)
        if not blob:
            raise HTTPException(404, "no trace for decision")
        anchors = db.anchors_for_decision(conn, decision_id)
    return {
        "decision_id": decision_id,
        "trace_hash": blob["trace_hash"],
        "canonical_json": blob["canonical_json"],
        "trace": json.loads(blob["canonical_json"]),
        "anchors": anchors,
    }


@app.get("/api/portfolio")
def portfolio() -> dict[str, Any]:
    with db.connect() as conn:
        positions = db.all_positions(conn)
        open_pos = [p for p in positions if p["status"] == "open"]
        realized = sum(p["pnl"] or 0 for p in positions if p["status"] == "closed")
    return {
        "positions": positions,
        "open_count": len(open_pos),
        "realized_pnl": realized,
        "bankroll": settings.agent_bankroll,
    }


@app.get("/api/metrics")
def metrics() -> dict[str, Any]:
    arc = get_arc()
    with db.connect() as conn:
        ms = db.latest_metrics(conn)
        cost_today = db.llm_cost_today(conn)
        anchors = db.recent_anchors(conn, limit=100)
    return {
        "metrics": ms,
        "llm_cost_today": cost_today,
        "anchor_count": sum(1 for a in anchors if a["kind"] == "anchor"),
        "settle_count": sum(1 for a in anchors if a["kind"] == "settle"),
        "real_tx_count": sum(1 for a in anchors if not a["mocked"]),
        "usdc_balance": arc.usdc_balance(),
        "model": settings.bedrock_model_id,
    }


@app.get("/api/anchors")
def anchors(limit: int = 50) -> dict[str, Any]:
    with db.connect() as conn:
        return {"anchors": db.recent_anchors(conn, limit=limit)}
