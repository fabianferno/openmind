"""Graph assembly: cap size, compute stats, and summarise for the reasoning prompt."""

from __future__ import annotations

from typing import Any

from agent.config import settings


def build_graph(
    ontology: dict[str, Any],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    max_nodes: int | None = None,
) -> dict[str, Any]:
    """Cap to the highest-degree `max_nodes`, drop dangling edges, compute stats."""
    cap = max_nodes or settings.graphrag_max_nodes
    ranked = sorted(nodes, key=lambda n: n.get("degree", 0), reverse=True)
    kept = ranked[:cap]
    keep_ids = {n["id"] for n in kept}
    kept_edges = [e for e in edges if e["source"] in keep_ids and e["target"] in keep_ids]

    type_counts: dict[str, int] = {}
    for n in kept:
        type_counts[n["type"]] = type_counts.get(n["type"], 0) + 1

    central = [
        {"label": n["label"], "type": n["type"], "degree": n.get("degree", 0)}
        for n in kept[:5]
    ]
    stats = {
        "node_count": len(kept),
        "edge_count": len(kept_edges),
        "type_counts": type_counts,
        "central": central,
        "entity_types": ontology["entity_types"],
        "relation_types": ontology["relation_types"],
    }
    return {"ontology": ontology, "nodes": kept, "edges": kept_edges, "stats": stats}


def summarize_for_prompt(graph: dict[str, Any]) -> str:
    """Compact textual summary injected into the entry-reasoning prompt."""
    stats = graph["stats"]
    nodes_by_key = {n["id"]: n for n in graph["nodes"]}
    central = ", ".join(
        f"{c['label']} ({c['type']}, {c['degree']} links)" for c in stats["central"]
    ) or "none"

    rel_lines: list[str] = []
    for e in graph["edges"][:18]:
        s = nodes_by_key.get(e["source"], {}).get("label", e["source"])
        t = nodes_by_key.get(e["target"], {}).get("label", e["target"])
        rel_lines.append(f"  {s} —{e['type']}→ {t}")
    rels = "\n".join(rel_lines) or "  (no relations extracted)"

    return (
        f"Knowledge graph built from date-bounded evidence: "
        f"{stats['node_count']} entities, {stats['edge_count']} relations.\n"
        f"Most-connected entities: {central}.\n"
        f"Key relationships:\n{rels}"
    )
