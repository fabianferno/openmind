"""Ontology generation — one LLM call that designs a per-market entity/relation schema."""

from __future__ import annotations

from typing import Any

from agent.config import settings
from agent.graphrag import prompts
from agent.logging import get_logger
from agent.reasoning import claude_client

log = get_logger(__name__)


def generate_ontology(
    market: dict[str, Any],
    search_hits: list[dict[str, Any]],
    *,
    llm: claude_client.BedrockClient | None = None,
) -> tuple[dict[str, Any] | None, claude_client.LLMResponse | None]:
    """Design an ontology for `market` from its evidence. Returns (ontology, llm_response)."""
    llm = llm or claude_client.get_client()
    corpus = prompts.build_corpus(search_hits)
    prompt = prompts.build_ontology_prompt(market, corpus)
    resp = llm.complete_json(
        system=prompts.ONTOLOGY_SYSTEM,
        user=prompt,
        model=settings.cheap_model,   # ontology design is easy → cheap model
        max_tokens=500,
        temperature=0.1,
    )
    ontology = prompts.validate_ontology(resp.parsed)
    if ontology is None:
        log.warning("graphrag.ontology_unparseable", market_id=market.get("id"))
    return ontology, resp
