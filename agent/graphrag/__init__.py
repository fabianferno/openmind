"""openmind GraphRAG: build an ontology + entity knowledge graph per market.

Pipeline:  ontology design (cheap LLM) → entity/relation extraction (main LLM)
           → assemble + cap + stats → compact summary for the reasoning prompt.

`build_market_graph` is the single entry point used by both the entry pipeline and the
streaming API. Pass an `emit` callback to receive ordered progress events for live UI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agent.config import settings
from agent.graphrag import extract as _extract
from agent.graphrag import graph as _graph
from agent.graphrag import ontology as _ontology
from agent.logging import get_logger
from agent.reasoning import claude_client

log = get_logger(__name__)

EmitFn = Callable[[str, dict[str, Any]], None]


@dataclass(slots=True)
class GraphResult:
    ontology: dict[str, Any]
    graph: dict[str, Any]                 # {ontology, nodes, edges, stats}
    summary: str
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def build_market_graph(
    market: dict[str, Any],
    search_hits: list[dict[str, Any]],
    *,
    as_of: datetime,
    emit: EmitFn | None = None,
    llm: claude_client.BedrockClient | None = None,
) -> GraphResult | None:
    """Build the knowledge graph for one market. Returns None if it can't be built."""
    def _emit(event: str, data: dict[str, Any]) -> None:
        if emit:
            try:
                emit(event, data)
            except Exception:  # never let UI streaming break the pipeline
                log.warning("graphrag.emit_failed", event=event)

    llm = llm or claude_client.get_client()
    cost = 0.0
    in_tok = 0
    out_tok = 0

    ontology, oresp = _ontology.generate_ontology(market, search_hits, llm=llm)
    if oresp:
        cost += oresp.cost_usd
        in_tok += oresp.input_tokens
        out_tok += oresp.output_tokens
    if not ontology:
        return None
    _emit("ontology_generated", {
        "entity_types": ontology["entity_types"],
        "relation_types": ontology["relation_types"],
    })

    nodes, edges, eresp = _extract.extract_graph(
        market, ontology, search_hits, as_of=as_of, llm=llm
    )
    cost += eresp.cost_usd
    in_tok += eresp.input_tokens
    out_tok += eresp.output_tokens
    if not nodes:
        return None

    graph = _graph.build_graph(ontology, nodes, edges, max_nodes=settings.graphrag_max_nodes)

    # stream the assembled graph node-by-node then edge-by-edge for the build animation
    for n in graph["nodes"]:
        _emit("entity_extracted", {"node": n})
    for e in graph["edges"]:
        _emit("relation_extracted", {"edge": e})
    _emit("graph_complete", {"stats": graph["stats"]})

    summary = _graph.summarize_for_prompt(graph)
    return GraphResult(
        ontology=ontology,
        graph=graph,
        summary=summary,
        cost_usd=cost,
        input_tokens=in_tok,
        output_tokens=out_tok,
        nodes=graph["nodes"],
        edges=graph["edges"],
        stats=graph["stats"],
    )
