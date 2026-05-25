# openmind
**The prediction-market agent that shows its work — and proves it on-chain.**

![Demo animation](https://i.ibb.co/jPyT54Np/Screen-Recording2026-05-25at10-56-53-PM-ezgif-com-video-to-gif-converter.gif)


openmind is a multi-agentic swarm intelligence prediction engine, that **builds a knowledge graph** of who and what moves a prediction
market, reasons over that graph to a calibrated **+EV bet**, then **anchors its entire
reasoning trace on Arc and settles in USDC**. Not a black box — a glass one.

> Built for the **Agora Agents Hackathon (Canteen × Circle)** — settled on **Arc** with
> **USDC**. Tackles **RFB 02 — Prediction Market Trader Intelligence** and the research angle
> *"reasoning traces as the product, anchored on Arc."* It's built on top of
> [`openclob`](./prd.md), a phased autonomous prediction-market trading engine.

---

## Why it's different

Most trading agents emit a number. openmind emits an **auditable reasoning artifact**:

1. **GraphRAG reasoning, not vibes.** For each market, the agent designs a bespoke *ontology*
   (entity + relation types), extracts an *entity knowledge graph* from date-bounded news, and
   feeds a summary of that graph into the forecast — so the graph **drives** the decision. You
   watch it build, node by node, live.
2. **Verifiable on-chain traces.** The full trace (ontology + graph + evidence + decision) is
   canonicalised, hashed (sha256), and the hash is **anchored on Arc**. Anyone can re-hash the
   trace in their browser and confirm it matches the chain. A symbolic **USDC stake is settled**
   on Arc per trade.
3. **A real autonomous engine underneath.** Filters → ambiguity check → date-bounded Tavily
   search (temporal-guarded against leakage) → graph-augmented reasoning → calibrated fractional
   Kelly sizing → paper/dry-run execution. Circuit breakers the LLM cannot bypass.

Cheap by design: reasoning runs on **Amazon Nova** via Bedrock — a full analyze costs ~**$0.015**.

## Proof: real Arc testnet transactions

These were produced by the agent during development (chain id `5042002`, gas paid in USDC):

| Kind | Tx | Explorer |
|------|----|----------|
| Trace anchor | `0xc9c7017929fae9b8…09f74bf5` | [arcscan](https://testnet.arcscan.app/tx/0xc9c7017929fae9b8e7960e62dae55e3bf3a65e1f758c2e68613fb4a609f74bf5) |
| USDC settle | `0xbece3ee590e15dc1…5bd2cb1c` | [arcscan](https://testnet.arcscan.app/tx/0xbece3ee590e15dc107d51ba5701d3b0a3dda12d91e5524cfe71704ff5bd2cb1c) |
| Trace anchor | `0x6e4b2c6d8bd33ca0…cbe592a7` | [arcscan](https://testnet.arcscan.app/tx/0x6e4b2c6d8bd33ca0f0d2a149af413fd5ee00c3e1c9b17766554de778cbe592a7) |

## Demo flow (the ≤3-min video)

Pick a market → watch the **Reasoning Room** build the ontology and entity graph live →
see the decision (P(YES) vs market price, edge, Kelly size) → it executes on Manifold and
**settles + anchors on Arc** → open the **Verify** page to re-hash the trace and match it
against the on-chain anchor.

## Architecture

```
Next.js + Tailwind + shadcn-style UI   (Terminal · Reasoning Room · Verify · Ledger)
        ▲  SSE (live build stream)      │  REST (history)
        │                               ▼
FastAPI sidecar  (agent/api)  ── streams ontology→entities→graph→decision→settled→anchored
        │                               │
EXISTING openclob engine  ───────▶  NEW agent/graphrag/   (ontology → entities → graph)
(data/reasoning/strategy/             graph summary feeds the entry reasoning prompt
 execution/store/monitor)                   │
        │                                   ▼
NEW agent/onchain/  (web3.py → Arc testnet: anchor trace hash + settle USDC)
        ▼
SQLite (+ graph_runs/nodes/edges, trace_blobs, onchain_anchors)
```

Design spec: [`docs/superpowers/specs/2026-05-25-openmind-graphrag-prediction-agent-design.md`](./docs/superpowers/specs/2026-05-25-openmind-graphrag-prediction-agent-design.md).

## Quick start

**1. Backend (Python 3.11+, uses [uv](https://github.com/astral-sh/uv)):**

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env        # fill in AWS (Bedrock/Nova), Tavily, ARC_TESTNET_WALLET_PRIVATE_KEY
mkdir -p data logs
python -m agent init-db

# run the API sidecar
uvicorn agent.api.server:app --port 8000
```

Fund the Arc wallet with testnet USDC from <https://faucet.circle.com/> (select Arc Testnet).
Without `ARC_ENABLED`/a key, on-chain calls degrade to clearly-flagged mock txns.

**2. Frontend (Node 18+):**

```bash
cd web
npm install
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
npm run dev        # http://localhost:3000
```

**3. Seed demo markets (optional, for reliable replay):**

```bash
python -m tools.seed_demo            # auto-pick top open markets
# or: python -m tools.seed_demo manifold:<id> ...
```

## How it maps to the judging criteria

- **Agentic sophistication (30%)** — the agent autonomously designs an ontology, builds a graph,
  reasons, sizes with Kelly, executes, *and* settles on-chain. End to end, no human in the loop.
- **Circle / Arc tooling (20%)** — real USDC settlement + trace anchoring on Arc testnet, gas in
  USDC, arcscan-verifiable. `agent/onchain/arc.py`.
- **Innovation (20%)** — verifiable reasoning traces as the product (research angle #1) + GraphRAG
  applied to prediction-market forecasting.
- **Traction (30%)** — honest: a POC built in the final window, with real on-chain testnet txns.

## The underlying engine (openclob)

openmind is built on the openclob trading agent. Its phased build, strategy, safety invariants,
and metric gates live in [`prd.md`](./prd.md) and [`CLAUDE.md`](./CLAUDE.md). Highlights:

- Continuous buy/sell of YES/NO shares (not bet-and-hold); entry **and** exit decisions each cycle.
- Temporal-guard leakage prevention on all search (`agent/reasoning/temporal_guard.py`).
- Hard-coded circuit breakers the LLM cannot bypass (`agent/execution/safety.py`).
- Modes: `backtest | paper (Manifold) | dryrun | live (Polymarket)` via `AGENT_MODE`.

```bash
python -m agent cycle        # one autonomous cycle (discovery → reason → trade)
pytest                       # 45 tests
```

> **Not financial advice.** Skill-validation / research project; paper + dry-run by default.
