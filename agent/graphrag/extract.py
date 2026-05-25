"""Entity + relationship extraction — one LLM call that fills in the ontology."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.config import settings
from agent.graphrag import prompts
from agent.logging import get_logger
from agent.reasoning import claude_client
from agent.reasoning.temporal_guard import filter_results

log = get_logger(__name__)


def extract_graph(
    market: dict[str, Any],
    ontology: dict[str, Any],
    search_hits: list[dict[str, Any]],
    *,
    as_of: datetime,
    llm: claude_client.BedrockClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], claude_client.LLMResponse]:
    """Extract (nodes, edges) for `market` constrained to `ontology`. Temporally guarded."""
    llm = llm or claude_client.get_client()
    corpus = prompts.build_corpus(search_hits)
    prompt = prompts.build_extract_prompt(
        market, ontology, corpus, max_nodes=settings.graphrag_max_nodes
    )
    resp = llm.complete_json(
        system=prompts.EXTRACT_SYSTEM,
        user=prompt,
        max_tokens=2200,
        temperature=0.1,
    )
    nodes, edges = prompts.validate_graph(resp.parsed, ontology, search_hits)

    # Defence in depth: drop any node/edge whose attached evidence post-dates as_of.
    # (The corpus is already date-bounded upstream; entities are usually undated, so we
    #  allow undated through and only reject explicitly post-dated provenance.)
    nodes = filter_results(nodes, as_of, allow_undated=True)
    edges = filter_results(edges, as_of, allow_undated=True)
    keep = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in keep and e["target"] in keep]

    log.info(
        "graphrag.extracted",
        market_id=market.get("id"), nodes=len(nodes), edges=len(edges),
    )
    return nodes, edges, resp
