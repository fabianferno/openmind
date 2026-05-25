# openmind — Design Spec

**Working title:** `openmind` — *the prediction-market agent that shows its work, and proves it on-chain.*
**Date:** 2026-05-25
**Status:** Approved direction, pre-implementation
**Context:** Submission for the **Agora Agents Hackathon (Canteen × Circle)**, settled on **Arc** with **USDC**. Built on top of the existing `openclob` engine. Deadline ≈ morning of 2026-05-26 IST — this is an **overnight build**, optimized for a strong public repo + a ≤3-min video demo + a live deployed link. Traction (the 30% axis that needs real users during the now-closed 2-week window) is not realistically winnable; we lean into **Agentic Sophistication (30%)**, **Circle/Arc tooling (20%)**, and **Innovation (20%)**.

---

## 1. What we're building

A **GraphRAG Alpha Terminal where every reasoning trade is verifiable on Arc.**

A user picks a prediction market. The agent:
1. builds an **ontology + entity knowledge graph** live from date-bounded news/search (the MiroFish-inspired "wow"),
2. reasons over that graph to a **+EV call** and a **Kelly-sized position**,
3. **executes** (paper on Manifold / dryrun on Polymarket),
4. **anchors the full reasoning-trace hash on Arc** and **settles USDC** on Arc,
5. streams all of this to a Next.js UI as a live "Reasoning Room," and exposes a **Verify** view where the trace is re-hashed client-side and matched against the on-chain anchor.

This maps to hackathon **RFB 02 (Prediction Market Trader Intelligence)** and research angle **#1 (reasoning traces as the product, anchored on Arc)**.

### Non-goals (deliberate scope cuts for one night)
- **No MiroFish fork.** MiroFish is AGPL-3.0 (would force our repo AGPL), depends on Zep Cloud, and ships a Flask+Vue stack plus a CAMEL/OASIS multi-agent simulator we don't need. We **reimplement** a lightweight ontology→GraphRAG pipeline inspired by it; we clone it only as a local reference.
- **No backend rewrite.** The Python `openclob` engine is ~85% complete and production-grade. We keep it. We do **not** migrate it to Node.
- **No IPFS/Irys pinning.** The full trace JSON is served by the API and re-hashed client-side — enough to demonstrate "verifiable." (IPFS is roadmap.)
- **No real money.** Paper (Manifold) + dryrun (Polymarket) only.
- **No auth / multi-user.** Single operator.
- **No CCTP / Gateway / cross-chain.** A single-chain Arc anchor + USDC settlement is enough for the Circle-tooling axis.

---

## 2. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| North star | GraphRAG Alpha Terminal **+** verifiable reasoning trades | The terminal is the product shell; the verifiable trade is what happens inside it. |
| MiroFish | Reimplement-inspired, **not** fork | AGPL + Zep + Vue + OASIS baggage we don't need. |
| Engine language | **Python** (keep openclob) | 85% done, production-grade; rewriting wastes the biggest asset. |
| LLM | **Amazon Nova Lite** via existing **AWS Bedrock** | Cheap, zero new keys; openclob's LLM client already speaks the Bedrock Converse API → swap model ID + token-cost constants only. |
| On-chain | **Python `web3.py`**, inside the agent | Arc is plain EVM; keeps the whole live pipeline in one SSE stream; strongest "agent settles autonomously" narrative. |
| Demo realness | **Live agent + pre-seeded markets** | Real autonomy + reliable video. Same render path for replay and live. |
| Arc depth | **Real testnet anchor + real USDC settle**, behind an interface with a mock fallback | Maximizes Circle-tooling score; genuine on-chain txns to point to. |
| Frontend | **Next.js + Tailwind + shadcn/ui** in **`web/`** (monorepo) | One public repo to submit. |
| Name | **openmind** | Per operator. |

### Credentials on hand
AWS Bedrock (Nova Lite), Tavily, and an Arc testnet wallet funded with USDC. Manifold public endpoints need no key.

---

## 3. Architecture

```
Next.js + Tailwind + shadcn   ("Alpha Terminal" + "Reasoning Room" + "Verify")
        ▲  SSE (live build stream)   │  REST/JSON (history)
        │                            ▼
FastAPI sidecar  (agent/api/server.py) — wraps existing fns, streams events, reads SQLite
        │                            │
EXISTING openclob engine  ───────▶  NEW  agent/graphrag/   (ontology → entities → graph)
(data/ reasoning/ strategy/          graph summary fed back into entry reasoning
 execution/ store/ monitor)                 │
        │                                    ▼
NEW  agent/onchain/arc.py  (web3.py → Arc testnet: anchor_trace + settle_usdc)
        ▼
SQLite (existing tables + NEW: graph_nodes, graph_edges, onchain_anchors, trace_blobs)
```

The existing per-market pipeline (`strategy/entry.py::plan_entry`) is: `filters → ambiguity check → date-bounded Tavily search → entry reasoning (Bedrock) → Kelly sizing → decision → execute`. We **insert GraphRAG between search and entry reasoning**, and **append anchor + settle after execution**.

---

## 4. New / changed components

### 4.1 `agent/graphrag/` (NEW) — the wow piece
- **`ontology.py`** — `generate_ontology(market, search_hits) -> Ontology`. One Bedrock (Nova Lite) call: given the market question + a corpus built from the date-bounded search hits, design a per-market ontology — entity types in `PascalCase` (≤10, last two catch-all) and relation types in `UPPER_SNAKE_CASE`. Strict validator (mirror the existing `prompts.validate_*` style) normalizes casing and caps counts.
- **`extract.py`** — `extract_graph(ontology, search_hits, as_of) -> (nodes, edges)`. One Bedrock call: extract entities + relationships conforming to the ontology, each carrying a **source citation + published date**. Every node/edge runs through the existing `reasoning/temporal_guard.py` (drop anything dated after `as_of`) → no leakage.
- **`graph.py`** — assemble nodes/edges into a graph, compute stats (counts, top-degree "central" entities), persist, and produce two serializations: (a) a compact text summary for the reasoning prompt, (b) a JSON `{nodes, edges, stats}` for the UI.
- **Functional, not decorative:** the compact graph summary is injected into the entry-reasoning prompt in `strategy/entry.py`, so the graph **drives** the decision. This is what lifts it above "AI-flavored automation" on the 30% axis.

### 4.2 `agent/onchain/arc.py` (NEW) — Arc settlement
- **`build_trace(decision_id) -> dict`** — canonical reasoning trace = `{market, ontology, graph, evidence/citations, decision (p_yes, edge, size, action), as_of, model}`.
- **`trace_hash(trace) -> 0x…`** — deterministic hash (keccak256 over canonical JSON). Persist the full trace blob (`trace_blobs`) so the API can serve it and the UI can re-hash → match.
- **`anchor_trace(decision_id) -> {tx_hash, explorer_url}`** — submit an Arc tx carrying the hash. Primary: tiny `Anchor.sol` emitting `TraceAnchored(bytes32 traceHash, string decisionId, uint256 ts)`. Fallback: plain tx with hash in calldata to a void address (no deploy needed).
- **`settle_usdc(amount, to) -> {tx_hash, explorer_url}`** — real ERC-20 USDC transfer on Arc (USDC `0x3600…0000`, 6 decimals) representing a symbolic per-trade stake/fee to a treasury wallet, so the demo has genuine USDC movement.
- All wrapped behind a small interface with a **mock implementation** (returns realistic-looking tx hashes + a flag) selected by env when `ARC_ENABLED=false`, so the build is never blocked by RPC issues.
- **Arc params (verify at impl time via `arc-canteen rpc-url`; sources were slightly inconsistent):** EVM chain ID `5042002`, RPC `https://rpc.testnet.arc.network` (or Canteen-hosted), USDC ERC-20 `0x3600000000000000000000000000000000000000` (6 decimals), faucet `https://faucet.circle.com/`, explorer `https://testnet.arcscan.app`. Gas is paid in USDC — no native token needed.

### 4.3 `agent/api/server.py` (NEW) — FastAPI sidecar
- `GET /markets` — candidate markets (discovery + DB).
- `POST /analyze/{market_id}` **(SSE)** — runs the live pipeline for one market and streams ordered events:
  `filter_passed → ontology_generated{schema} → entity_extracted{node|edge}… → graph_complete{stats} → evidence{citations} → decision{p_yes,price,edge,size,action} → executed{venue,order} → anchored{tx} → settled{tx}`.
  This drives the Reasoning Room animation. Supports a `?replay=seedId` mode that emits cached events (with the real, already-mined Arc tx links) on a timer.
- `POST /cycle` — runs a genuine full `run_cycle()` (the "run now" button).
- `GET /portfolio`, `GET /metrics`, `GET /decisions/{id}`, `GET /trace/{id}` — read SQLite.
- CORS for the Next.js origin.

### 4.4 Existing files — minimal edits
- **`agent/reasoning/claude_client.py`** — point default model at Nova Lite (`BEDROCK_MODEL_ID`), keep Converse API; update `LLM_INPUT/OUTPUT_USD_PER_MTOK`. (Optional cosmetic alias `llm_client`; skip if time-poor.)
- **`agent/strategy/entry.py`** — call graphrag between search and entry reasoning; pass the graph summary into the prompt; attach graph + onchain refs to the returned plan / decision record.
- **`agent/store/schema.sql` + `db.py`** — add `graph_nodes`, `graph_edges`, `onchain_anchors`, `trace_blobs` tables + DAO fns.
- **`agent/config.py`** — add `ARC_ENABLED`, `ARC_RPC_URL`, `ARC_CHAIN_ID`, `ARC_PRIVATE_KEY`, `ARC_USDC_ADDRESS`, `ARC_ANCHOR_CONTRACT`, `ARC_TREASURY_ADDRESS`, `ARC_SETTLE_USDC` (symbolic amount), `WEB_ORIGIN`.
- **`pyproject.toml`** — add `fastapi`, `uvicorn`, `sse-starlette` (or stream via `StreamingResponse`). `web3` already present.

### 4.5 `web/` (NEW) — Next.js frontend
- **Terminal home** — market cards (question, price, volume, category) + "Analyze"; portfolio + Brier/ECE/PnL gauges; a "Run a live cycle" button.
- **Reasoning Room** (the hero, ~90s of the video):
  - Left: ontology schema appearing as chips (entity types, relation types) with framer-motion.
  - Center: force-directed entity graph growing node-by-node as `entity_extracted` events stream (`react-force-graph`).
  - Right: evidence feed (date-bounded citations) → decision card (p_yes vs market price, edge, Kelly size, action) → on-chain panel (*anchoring… → arcscan tx link → USDC settled → arcscan tx link*).
- **Verify page** — render the full trace, re-hash it client-side, and show ✅ match against the on-chain anchor (read the event from Arc / show the tx). The "verifiable" payoff.
- **Portfolio/metrics page** — positions, PnL, calibration chart.
- Stack: Next.js (app router), Tailwind, shadcn/ui, framer-motion, react-force-graph, `EventSource` for SSE.

---

## 5. Data flow (one "Analyze")

```
market
  → filters.passes_all
  → ambiguity check (Nova Lite)
  → date-bounded Tavily search (temporal_guard)
  → graphrag.ontology.generate_ontology         [SSE: ontology_generated]
  → graphrag.extract.extract_graph              [SSE: entity_extracted…]
  → graphrag.graph.build + summary              [SSE: graph_complete, evidence]
  → entry reasoning (Nova Lite, graph-augmented)→ Kelly sizing  [SSE: decision]
  → executor.place_entry (paper/dryrun)         [SSE: executed]
  → onchain.build_trace → trace_hash → anchor_trace(Arc)  [SSE: anchored]
  → onchain.settle_usdc(Arc)                    [SSE: settled]
  → persist everything to SQLite (decisions, graph_*, onchain_anchors, trace_blobs)
```

---

## 6. Reliability via seeding
Pre-run 3–5 hand-picked markets end-to-end with their **Arc txns actually executed on testnet** (real, mined, linkable on arcscan), and cache each event stream. The Reasoning Room **replays** a seeded market deterministically for the clean video take; the **"run now"** path does a genuine live SSE cycle. Identical rendering.

---

## 7. Testing (scaled to the night)
- Unit: ontology/extract JSON parsing + validators; graph assembly + summary; `trace_hash` determinism; mock vs real onchain interface selection.
- Existing `tests/` must stay green.
- One real end-to-end `analyze` against a live Manifold market, producing **real Arc anchor + USDC settle** txns (capture the arcscan links for the README + video).

---

## 8. Risks & fallbacks
| Risk | Fallback |
|---|---|
| Arc RPC / deploy flaky | `ARC_ENABLED=false` mock interface (realistic tx hashes + badge); or calldata-only anchor (no contract deploy). |
| Nova Lite returns malformed JSON | Existing tolerant 3-pass JSON extraction + strict validators; one retry; skip market on repeated failure. |
| Live reasoning unavailable mid-demo | Seeded replay (still real — generated for real earlier). |
| Graph too dense to render | Cap nodes (~25–40); keep top-degree entities. |
| Time runs out | Priority order in §9; the Reasoning Room + a single real anchored+settled trace is the minimum lovable demo. |

---

## 9. Build priority (most demo value first)
1. **Nova Lite swap** + smoke-test one live `plan_entry` (proves reasoning works cheaply).
2. **`agent/graphrag/`** (ontology + extract + graph) + wire into `entry.py` + new tables.
3. **FastAPI `/analyze` SSE** emitting the full event sequence.
4. **Next.js Reasoning Room** consuming SSE (ontology chips + growing graph + decision card).
5. **`agent/onchain/arc.py`** real anchor + USDC settle + `anchored`/`settled` events + Verify page.
6. **Seeding** 3–5 markets with real Arc txns; portfolio/metrics page; polish; record video.

---

## 10. Submission checklist
- Public repo (monorepo: `agent/` + `web/`), README with the openmind story, arcscan tx links, and architecture diagram.
- ≤3-min video: pick market → Reasoning Room builds graph → decision → anchor+settle on Arc → Verify.
- Live deployed link (Vercel for `web/`; FastAPI on a small host or tunneled).
- Written traction report (honest: POC + N real on-chain testnet txns during the window).
