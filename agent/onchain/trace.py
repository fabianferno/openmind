"""Reasoning-trace canonicalisation + hashing.

The trace is the *product*: ontology + graph + evidence + decision. We serialise it to a
canonical string, hash that string (sha256), anchor the hash on Arc, and store the exact
canonical bytes so the UI can re-hash and verify the on-chain anchor.

Pure functions only — no web3, no DB. Easy to unit-test for determinism.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_trace(
    *,
    market: dict[str, Any],
    decision: dict[str, Any],
    graph: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the canonical reasoning trace from primitive dicts."""
    g = graph or {}
    stats = g.get("stats", {})
    return {
        "schema": "openmind.trace.v1",
        "market": {
            "id": market.get("id"),
            "venue": market.get("venue"),
            "question": market.get("question"),
            "category": market.get("category"),
            "end_date": market.get("end_date"),
            "market_price_yes": market.get("last_price_yes"),
        },
        "decision": {
            "id": decision.get("id"),
            "as_of": decision.get("as_of"),
            "model_id": decision.get("model_id"),
            "p_yes": decision.get("p_yes"),
            "confidence": decision.get("confidence"),
            "edge_vs_market": decision.get("edge"),
            "action": decision.get("action"),
            "rationale": decision.get("rationale"),
        },
        "graph": {
            "ontology": g.get("ontology"),
            "node_count": stats.get("node_count"),
            "edge_count": stats.get("edge_count"),
            "nodes": [
                {"id": n["id"], "label": n["label"], "type": n["type"]}
                for n in g.get("nodes", [])
            ],
            "edges": [
                {"source": e["source"], "target": e["target"], "type": e["type"]}
                for e in g.get("edges", [])
            ],
        },
        "evidence": [
            {"url": h.get("url"), "title": h.get("title"),
             "published_date": h.get("published_date")}
            for h in evidence
        ],
    }


def canonical(trace: dict[str, Any]) -> str:
    """Deterministic JSON string. The UI hashes this exact string to verify."""
    return json.dumps(trace, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def trace_hash(canonical_str: str) -> str:
    """0x-prefixed sha256 of the canonical string."""
    return "0x" + hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
