"""Tests for openmind additions: GraphRAG validators, trace hashing, Arc mock fallback."""

from __future__ import annotations

from agent.graphrag import graph as graph_mod
from agent.graphrag.prompts import validate_graph, validate_ontology
from agent.onchain import trace as trace_mod


def test_validate_ontology_normalises_casing():
    o = validate_ontology({
        "entity_types": ["poli tician", "Org", "org"],   # dup collapses
        "relation_types": ["endorses", "member of"],
    })
    assert o is not None
    assert o["entity_types"][1] == "Org"
    assert "ENDORSES" in o["relation_types"]
    assert "MEMBER_OF" in o["relation_types"]


def test_validate_ontology_rejects_garbage():
    assert validate_ontology({"entity_types": [], "relation_types": []}) is None
    assert validate_ontology("nope") is None


def test_validate_graph_drops_dangling_edges_and_attaches_sources():
    ont = {"entity_types": ["Politician", "Party"], "relation_types": ["MEMBER_OF"]}
    hits = [{"url": "http://a", "published_date": "2026-01-01"}]
    nodes, edges = validate_graph(
        {
            "nodes": [
                {"id": "trump", "label": "Trump", "type": "Politician", "evidence": 1},
                {"id": "gop", "label": "GOP", "type": "Party", "evidence": 1},
            ],
            "edges": [
                {"source": "trump", "target": "gop", "type": "MEMBER_OF", "evidence": 1},
                {"source": "trump", "target": "ghost", "type": "MEMBER_OF"},  # dangling
            ],
        },
        ont, hits,
    )
    assert len(nodes) == 2
    assert len(edges) == 1
    assert edges[0]["source_url"] == "http://a"
    # degree updated on both endpoints
    assert {n["label"]: n["degree"] for n in nodes} == {"Trump": 1, "GOP": 1}


def test_validate_graph_coerces_unknown_types():
    ont = {"entity_types": ["Politician", "Other"], "relation_types": ["ENDORSES"]}
    nodes, edges = validate_graph(
        {
            "nodes": [
                {"id": "x", "label": "X", "type": "Alien", "evidence": 1},
                {"id": "y", "label": "Y", "type": "Politician", "evidence": 1},
            ],
            "edges": [{"source": "x", "target": "y", "type": "HATES", "evidence": 1}],
        },
        ont, [{"url": "u", "published_date": None}],
    )
    assert nodes[0]["type"] == "Other"            # unknown → catch-all (last entity type)
    assert edges[0]["type"] == "RELATED_TO"       # unknown relation → RELATED_TO


def test_build_graph_caps_nodes_by_degree():
    ont = {"entity_types": ["E"], "relation_types": ["R"]}
    nodes = [{"id": f"n{i}", "label": f"N{i}", "type": "E", "degree": i} for i in range(10)]
    edges = [{"source": "n8", "target": "n9", "type": "R"}]
    g = graph_mod.build_graph(ont, nodes, edges, max_nodes=3)
    assert g["stats"]["node_count"] == 3
    kept = {n["id"] for n in g["nodes"]}
    assert kept == {"n9", "n8", "n7"}             # highest degree retained
    assert len(g["edges"]) == 1                   # edge between kept nodes survives


def test_trace_hash_is_deterministic_and_order_independent():
    t1 = trace_mod.build_trace(
        market={"id": "m", "question": "q"},
        decision={"id": 1, "p_yes": 0.6},
        graph={"ontology": {"entity_types": ["A"], "relation_types": ["R"]},
               "stats": {"node_count": 1, "edge_count": 0},
               "nodes": [{"id": "a", "label": "A", "type": "A"}], "edges": []},
        evidence=[{"url": "u", "title": "t", "published_date": "2026-01-01"}],
    )
    # same inputs → same hash
    t2 = dict(t1)
    h1 = trace_mod.trace_hash(trace_mod.canonical(t1))
    h2 = trace_mod.trace_hash(trace_mod.canonical(t2))
    assert h1 == h2 and h1.startswith("0x") and len(h1) == 66


def test_arc_client_mock_when_disabled(monkeypatch):
    from agent.config import settings
    from agent.onchain.arc import ArcClient

    monkeypatch.setattr(settings, "arc_enabled", False)
    c = ArcClient()
    assert c.real is False
    res = c.anchor("0x" + "ab" * 32)
    assert res["mocked"] is True
    assert res["tx_hash"].startswith("0x")
    settle = c.transfer_usdc("0x" + "1" * 40, 0.01)
    assert settle["mocked"] is True
