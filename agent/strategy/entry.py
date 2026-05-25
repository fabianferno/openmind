"""Entry decision pipeline.

  market → filters → ambiguity check → search → entry reasoning → size → decision

The pipeline returns a `EntryPlan` whose `action` is one of:
  - 'skip': agent should not enter (with reason).
  - 'enter': agent should place an order at the chosen side + price + size.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agent import graphrag
from agent.config import settings
from agent.logging import get_logger
from agent.reasoning import claude_client, prompts, search
from agent.store import db as _db
from agent.strategy import calibration, filters, sizing

log = get_logger(__name__)

EmitFn = Callable[[str, dict[str, Any]], None]


@dataclass(slots=True)
class EntryPlan:
    action: str                          # 'enter' | 'skip'
    reason: str
    market_id: str
    side: str | None = None              # 'YES' or 'NO'
    target_price: float | None = None
    usd_size: float | None = None
    p_yes: float | None = None
    confidence: float | None = None
    edge: float | None = None
    rationale: str | None = None
    model_id: str | None = None
    decision_id: int | None = None
    search_results: list[dict[str, Any]] = field(default_factory=list)
    graph: dict[str, Any] | None = None  # {ontology, nodes, edges, stats}


SEARCH_QUERIES_PER_MARKET = 2  # broad + targeted; PRD §8.2 hard-caps at 8


def plan_entry(
    market: dict[str, Any],
    *,
    as_of: datetime | None = None,
    backtest: bool = False,
    relaxed: bool = False,
    emit: EmitFn | None = None,
) -> EntryPlan:
    """Run the full entry pipeline for one market.

    `emit(event, data)` (optional) receives ordered progress events for live UI streaming:
    filter_passed, ambiguity, search_complete, ontology_generated, entity_extracted,
    relation_extracted, graph_complete, evidence, decision.
    """
    as_of = as_of or datetime.now(UTC)
    market_id = market["id"]

    def _emit(event: str, data: dict[str, Any]) -> None:
        if emit:
            try:
                emit(event, data)
            except Exception:  # never let UI streaming break the pipeline
                log.warning("entry.emit_failed", event=event)

    # 1. cheap filters
    flt = filters.passes_all(market, now=as_of, backtest=backtest, relaxed=relaxed)
    if not flt.accepted:
        _emit("skip", {"reason": f"filter:{flt.reason}"})
        return EntryPlan("skip", f"filter:{flt.reason}", market_id)
    _emit("filter_passed", {"market_id": market_id, "question": market.get("question")})

    llm = claude_client.get_client()

    # 2. ambiguity check — skip in backtest mode (orthogonal to leakage semantics, and
    # weaker cheap models over-reject, which starves the Brier sample).
    amb_id: int | None = None
    if not backtest and not relaxed:
        amb_prompt = prompts.build_ambiguity_prompt(market)
        try:
            amb_resp = llm.complete_json(
                system=prompts.AMBIGUITY_SYSTEM,
                user=amb_prompt,
                model=settings.cheap_model,
                max_tokens=256,
                temperature=0.0,
            )
        except claude_client.BudgetExceeded as e:
            return EntryPlan("skip", f"budget:{e}", market_id)

        amb_parsed = prompts.validate_ambiguity(amb_resp.parsed)
        with _db.connect() as conn:
            amb_id = _db.record_decision(conn, {
                "market_id": market_id,
                "kind": "ambiguity",
                "as_of": as_of.isoformat(),
                "prompt": amb_prompt,
                "search_used": None,
                "model_id": amb_resp.model_id,
                "response_raw": amb_resp.text,
                "response_json": amb_parsed,
                "action": "skip" if not amb_parsed or not amb_parsed["unambiguous"] else "continue",
                "input_tokens": amb_resp.input_tokens,
                "output_tokens": amb_resp.output_tokens,
                "cost_usd": amb_resp.cost_usd,
            })
        if not amb_parsed:
            return EntryPlan("skip", "ambiguity_unparseable", market_id, decision_id=amb_id)
        if not amb_parsed["unambiguous"]:
            return EntryPlan("skip", f"ambiguous:{amb_parsed['rationale'][:80]}", market_id, decision_id=amb_id)

    # 3. search
    tav = search.get_client()
    hits: list[dict[str, Any]] = []
    try:
        broad = tav.search(market["question"], as_of=as_of, max_results=settings.tavily_max_results)
        hits.extend(h.to_dict() for h in broad)
        # targeted second pass: pull a key phrase from the question
        targeted_q = market["question"]
        if market.get("resolution_rules"):
            targeted_q = market["question"] + " " + market["resolution_rules"][:200]
        targeted = tav.search(targeted_q, as_of=as_of, max_results=4)
        hits.extend(h.to_dict() for h in targeted)
    except Exception as e:
        log.warning("entry.search_failed", market_id=market_id, error=str(e))

    # de-dup by URL
    seen_urls: set[str] = set()
    deduped = []
    for h in hits:
        u = h.get("url") or ""
        if u and u not in seen_urls:
            seen_urls.add(u)
            deduped.append(h)
    hits = deduped[: settings.tavily_max_results * 2]
    _emit("search_complete", {"n": len(hits)})

    # 3.5 GraphRAG — build an ontology + entity graph from the date-bounded evidence.
    # The graph summary is injected into the reasoning prompt so it *drives* the decision.
    graph_result = None
    graph_summary: str | None = None
    if settings.graphrag_enabled and hits:
        try:
            graph_result = graphrag.build_market_graph(
                market, hits, as_of=as_of, emit=emit, llm=llm
            )
            if graph_result:
                graph_summary = graph_result.summary
        except claude_client.BudgetExceeded as e:
            return EntryPlan("skip", f"budget:{e}", market_id, search_results=hits)
        except Exception as e:  # noqa: BLE001
            log.warning("entry.graphrag_failed", market_id=market_id, error=str(e))

    _emit("evidence", {"citations": [
        {"url": h.get("url"), "title": h.get("title"), "published_date": h.get("published_date")}
        for h in hits[:10]
    ]})

    # 4. entry reasoning (graph-augmented)
    market_price = float(market.get("last_price_yes") or 0.5)
    entry_prompt = prompts.build_entry_prompt(
        market, as_of=as_of, market_price_yes=market_price, search_results=hits,
        graph_summary=graph_summary,
    )
    try:
        entry_resp = llm.complete_json(
            system=prompts.ENTRY_SYSTEM,
            user=entry_prompt,
            max_tokens=1500,
            temperature=0.2,
        )
    except claude_client.BudgetExceeded as e:
        return EntryPlan("skip", f"budget:{e}", market_id)

    entry_parsed = prompts.validate_entry(entry_resp.parsed)
    with _db.connect() as conn:
        entry_id = _db.record_decision(conn, {
            "market_id": market_id,
            "kind": "entry",
            "as_of": as_of.isoformat(),
            "prompt": entry_prompt,
            "search_used": [{"url": h.get("url"), "title": h.get("title"),
                             "published": h.get("published_date")} for h in hits],
            "model_id": entry_resp.model_id,
            "response_raw": entry_resp.text,
            "response_json": entry_parsed,
            "p_yes": entry_parsed["p_yes"] if entry_parsed else None,
            "confidence": entry_parsed["confidence"] if entry_parsed else None,
            "action": entry_parsed["recommended_action"] if entry_parsed else "skip",
            "input_tokens": entry_resp.input_tokens,
            "output_tokens": entry_resp.output_tokens,
            "cost_usd": entry_resp.cost_usd,
        })
        # persist the graph against the entry decision it informed
        if graph_result:
            _db.save_graph(
                conn,
                decision_id=entry_id, market_id=market_id, as_of=as_of.isoformat(),
                ontology=graph_result.ontology, nodes=graph_result.nodes,
                edges=graph_result.edges, stats=graph_result.stats,
            )

    graph_payload = graph_result.graph if graph_result else None

    if not entry_parsed:
        return EntryPlan("skip", "entry_unparseable", market_id, decision_id=entry_id,
                         model_id=entry_resp.model_id, search_results=hits, graph=graph_payload)

    _emit("decision", {
        "decision_id": entry_id,
        "p_yes": entry_parsed["p_yes"],
        "market_price": market_price,
        "confidence": entry_parsed["confidence"],
        "edge": entry_parsed["edge_vs_market"],
        "action": entry_parsed["recommended_action"],
        "rationale": entry_parsed["rationale"],
    })

    if entry_parsed["recommended_action"] == "skip":
        return EntryPlan(
            "skip", "llm_skip", market_id,
            p_yes=entry_parsed["p_yes"], confidence=entry_parsed["confidence"],
            edge=entry_parsed["edge_vs_market"], rationale=entry_parsed["rationale"],
            model_id=entry_resp.model_id, decision_id=entry_id, search_results=hits,
            graph=graph_payload,
        )

    # 5. sizing
    cat = (market.get("category") or "uncategorised").lower()
    mul = calibration.multiplier_for(cat)
    sd = sizing.size_position(
        p_agent=entry_parsed["p_yes"],
        p_market=market_price,
        calibration_mul=mul,
    )
    if sd.usd <= 0:
        return EntryPlan("skip", f"sizing:{sd.reason}", market_id, decision_id=entry_id,
                         p_yes=entry_parsed["p_yes"], confidence=entry_parsed["confidence"],
                         edge=entry_parsed["edge_vs_market"], rationale=entry_parsed["rationale"],
                         model_id=entry_resp.model_id, search_results=hits, graph=graph_payload)

    # Side mapping: LLM said enter_yes/enter_no, sizing.side should agree
    llm_side = "YES" if entry_parsed["recommended_action"] == "enter_yes" else "NO"
    if sd.side != llm_side:
        return EntryPlan(
            "skip", f"side_mismatch:llm={llm_side} kelly={sd.side}",
            market_id, decision_id=entry_id, p_yes=entry_parsed["p_yes"],
            confidence=entry_parsed["confidence"], edge=entry_parsed["edge_vs_market"],
            rationale=entry_parsed["rationale"], model_id=entry_resp.model_id,
            search_results=hits, graph=graph_payload,
        )

    # target_price: place 1-3¢ inside spread on entry side
    if sd.side == "YES":
        target_price = max(0.02, min(0.98, market_price - 0.02))
    else:
        target_price = max(0.02, min(0.98, (1 - market_price) - 0.02))

    return EntryPlan(
        action="enter",
        reason="ok",
        market_id=market_id,
        side=sd.side,
        target_price=target_price,
        usd_size=sd.usd,
        p_yes=entry_parsed["p_yes"],
        confidence=entry_parsed["confidence"],
        edge=entry_parsed["edge_vs_market"],
        rationale=entry_parsed["rationale"],
        model_id=entry_resp.model_id,
        decision_id=entry_id,
        search_results=hits,
        graph=graph_payload,
    )
