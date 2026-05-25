"""Prompts + validators for the GraphRAG pipeline (ontology design + entity extraction).

Two LLM call types, mirroring the MiroFish approach but reimplemented from scratch:

  1. ontology  — design a per-market schema: entity types (PascalCase) + relation types
                 (UPPER_SNAKE_CASE), tailored to the market question and its evidence.
  2. extract   — pull entities + relationships out of the date-bounded evidence, each
                 carrying the evidence index it came from (so we can attach source + date).
"""

from __future__ import annotations

import re
from typing import Any

# ---------- system prompts ----------

ONTOLOGY_SYSTEM = (
    "You are a knowledge-graph ontologist for prediction-market analysis. "
    "Given a market question and supporting evidence, you design a compact ontology: the "
    "entity types and relationship types most useful for reasoning about who and what drives "
    "this market's outcome. Entity types are real-world subjects (people, organisations, "
    "places, events, policies, indicators). You reply ONLY with valid JSON."
)

EXTRACT_SYSTEM = (
    "You are a knowledge-graph extractor. Given an ontology and numbered evidence snippets, "
    "you extract the entities and the relationships between them that are relevant to the "
    "market. Use ONLY information present in the evidence. Every entity and relationship must "
    "cite the evidence index [n] it came from. You reply ONLY with valid JSON."
)


# ---------- user prompts ----------

def build_corpus(search_hits: list[dict[str, Any]], *, max_chars: int = 6000) -> str:
    if not search_hits:
        return "(no evidence)"
    lines: list[str] = []
    total = 0
    for i, r in enumerate(search_hits, start=1):
        date = r.get("published_date") or "undated"
        title = (r.get("title") or "")[:140]
        content = (r.get("content") or "")[:500].replace("\n", " ")
        block = f"[{i}] ({date}) {title} — {content}"
        if total + len(block) > max_chars:
            break
        lines.append(block)
        total += len(block)
    return "\n".join(lines)


def build_ontology_prompt(market: dict[str, Any], corpus: str) -> str:
    return f"""Market: {market["question"]}
Category: {market.get("category") or "unspecified"}

EVIDENCE:
{corpus}

Design an ontology for reasoning about this market. Choose 4-8 entity types and 4-8
relationship types that best capture the actors and forces at play. Be specific to THIS
market (e.g. for an election: Candidate, Party, PollingOrg; for monetary policy: CentralBank,
Indicator, Official).

Rules:
- entity_types: PascalCase nouns (e.g. "Politician", "Organization", "EconomicIndicator").
- relation_types: UPPER_SNAKE_CASE verbs (e.g. "ENDORSES", "MEMBER_OF", "INFLUENCES").

Respond in this exact JSON shape:
{{
  "entity_types": ["...", "..."],
  "relation_types": ["...", "..."]
}}"""


def build_extract_prompt(
    market: dict[str, Any], ontology: dict[str, Any], corpus: str, *, max_nodes: int
) -> str:
    ets = ", ".join(ontology["entity_types"])
    rts = ", ".join(ontology["relation_types"])
    return f"""Market: {market["question"]}

ONTOLOGY
  entity types:   {ets}
  relation types: {rts}

EVIDENCE (cite the [n] index for every entity and relationship):
{corpus}

Extract the knowledge graph. At most {max_nodes} entities. Prefer entities and relationships
that bear on whether the market resolves YES or NO.

For each entity: a short stable id (lowercase, hyphenated, e.g. "donald-trump"), a display
label, a type from the entity types above, a one-line summary, and the evidence index it came
from. For each relationship: source id, target id (both must be entities you listed), a type
from the relation types above, a one-line rationale, and the evidence index.

Respond in this exact JSON shape:
{{
  "nodes": [
    {{"id": "donald-trump", "label": "Donald Trump", "type": "Politician",
      "summary": "Republican nominee", "evidence": 1}}
  ],
  "edges": [
    {{"source": "donald-trump", "target": "republican-party", "type": "MEMBER_OF",
      "rationale": "Nominee of the party", "evidence": 1}}
  ]
}}"""


# ---------- normalisation helpers ----------

def _pascal(s: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", str(s).strip())
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Entity"


def _upper_snake(s: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", str(s).strip())
    return "_".join(p.upper() for p in parts if p) or "RELATED_TO"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).strip().lower()).strip("-") or "node"


# ---------- validators ----------

def validate_ontology(parsed: Any) -> dict[str, Any] | None:
    if not isinstance(parsed, dict):
        return None
    ents = parsed.get("entity_types")
    rels = parsed.get("relation_types")
    if not isinstance(ents, list) or not isinstance(rels, list) or not ents or not rels:
        return None
    entity_types = list(dict.fromkeys(_pascal(e) for e in ents if str(e).strip()))[:10]
    relation_types = list(dict.fromkeys(_upper_snake(r) for r in rels if str(r).strip()))[:12]
    if not entity_types or not relation_types:
        return None
    return {"entity_types": entity_types, "relation_types": relation_types}


def validate_graph(
    parsed: Any,
    ontology: dict[str, Any],
    search_hits: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (nodes, edges) normalised to the ontology, with source attribution attached.

    Unknown entity types are coerced to the last entity type (catch-all); unknown relation
    types to RELATED_TO. Edges referencing unknown node ids are dropped.
    """
    if not isinstance(parsed, dict):
        return [], []
    entity_types = ontology["entity_types"]
    relation_types = set(ontology["relation_types"])
    catchall = entity_types[-1]

    def _source(idx: Any) -> tuple[str | None, str | None]:
        try:
            hit = search_hits[int(idx) - 1]
            return hit.get("url"), hit.get("published_date")
        except (TypeError, ValueError, IndexError):
            return None, None

    nodes: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for n in parsed.get("nodes", []) or []:
        if not isinstance(n, dict) or not n.get("label"):
            continue
        key = _slug(n.get("id") or n["label"])
        if key in by_key:
            continue
        ntype = _pascal(n.get("type") or catchall)
        if ntype not in entity_types:
            ntype = catchall
        url, date = _source(n.get("evidence"))
        node = {
            "id": key,
            "label": str(n["label"])[:80],
            "type": ntype,
            "summary": str(n.get("summary", ""))[:200],
            "source_url": url,
            "published_date": date,
            "degree": 0,
        }
        by_key[key] = node
        nodes.append(node)

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for e in parsed.get("edges", []) or []:
        if not isinstance(e, dict):
            continue
        src = _slug(e.get("source") or "")
        tgt = _slug(e.get("target") or "")
        if src not in by_key or tgt not in by_key or src == tgt:
            continue
        etype = _upper_snake(e.get("type") or "RELATED_TO")
        if etype not in relation_types:
            etype = "RELATED_TO"
        sig = (src, tgt, etype)
        if sig in seen:
            continue
        seen.add(sig)
        url, date = _source(e.get("evidence"))
        edges.append({
            "source": src,
            "target": tgt,
            "type": etype,
            "rationale": str(e.get("rationale", ""))[:200],
            "source_url": url,
            "published_date": date,
        })
        by_key[src]["degree"] += 1
        by_key[tgt]["degree"] += 1

    return nodes, edges
