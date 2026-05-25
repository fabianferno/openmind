# openmind — Traction Report

*As of the submission window. Live counters update on the app: https://openthemind.vercel.app
(Ledger tab) and `GET /api/metrics`.*

## Headline

openmind produced **real, verifiable on-chain activity on Arc testnet during the hackathon
window** — not screenshots, not a mock. Every number below corresponds to a transaction you can
open on [arcscan](https://testnet.arcscan.app).

| Metric | Value |
|---|---|
| **Real Arc testnet transactions** | **40** |
| Reasoning traces anchored on-chain | **30** |
| USDC settlements | **10** (~0.10 USDC) |
| Distinct markets analyzed | **26** |
| Autonomous decisions recorded | **30** |
| LLM cost for all of it (Amazon Nova) | **$0.25** (~$0.008 / decision) |
| Mock fallbacks | 1 (a nonce race during a concurrent test) |

The economics are the point: anchoring an entire reasoning trace costs **~$0.01 in USDC** on Arc.
That's only viable because of Arc's sub-cent USDC fees + instant finality — on a normal L1 the
anchor would cost more than the trade.

## What "traction" means here (honest framing)

The judging rubric weights real users + real transactions. We're a final-window build, so:

- **What we have:** genuine on-chain volume on Arc (40 real txns), a live deployed app, a public
  repo, and a fully autonomous pipeline anyone can run. Each decision is independently verifiable.
- **What we don't (yet):** a real external user base or wagered volume. We're not going to dress up
  agent-generated activity as organic user growth.

## Sample verifiable transactions

Reasoning-trace anchors (open in arcscan, then re-verify on the app's `/verify/<id>` page):

- anchor · decision #218 — [`0xcad9a66f…c12e3f`](https://testnet.arcscan.app/tx/0xcad9a66fb4039338f9feffdaaa628b5dd42de5d494daf9c3bedaa56e35c12e3f)
- anchor · decision #217 — [`0xebc58d4c…42569a`](https://testnet.arcscan.app/tx/0xebc58d4c9b96fc75e067e4a8e5701e5ce335f2aa18baa1860b512b83cb42569a)
- anchor · decision #216 — [`0xd874c484…d15bff`](https://testnet.arcscan.app/tx/0xd874c484c5bba231ae3160c4a40b58dc78b8e445b6eedb46d7f82b7b81d15bff)

USDC settlements (real ERC-20 transfers on Arc):

- settle · decision #192 — [`0xbece3ee5…5bd2cb1c`](https://testnet.arcscan.app/tx/0xbece3ee590e15dc107d51ba5701d3b0a3dda12d91e5524cfe71704ff5bd2cb1c)
- settle · decision #190 — [`0x08f8cac0…38906b`](https://testnet.arcscan.app/tx/0x08f8cac007554619c816e467adb3662b1ff471031920bfd5e6dd69d93538906b)

Agent wallet: `0x5a09e3eC3EFDD91205Cbb097142a4f4dCEFc7f02` (Arc testnet, chain `5042002`).

## How it was produced (reproducible)

```bash
uvicorn agent.api.server:app --port 8000      # API
python -m tools.traction_run 25               # analyze 25 markets → real Arc txns
python -m tools.seed_demo                      # capture deterministic demo replays
```

Each market runs the full autonomous pipeline (ontology → graph → reasoning → sizing → execution →
anchor + settle). No human picks the markets in `traction_run`/`/api/auto`.

## Path to organic traction (post-hackathon)

1. **Agent-as-builder fees** — earn USDC builder fees on Polymarket fills the agent recommends
   (on-chain attribution, no custody). This is the natural monetization and the user-acquisition
   loop.
2. **Public "verified reasoning" feed** — every anchored decision is a shareable, verifiable call;
   the feed itself is the growth surface.
3. **Markets on the reasoning** — bet on which reasoning patterns convert to profit (research angle).

## Caveats we own

- Settlement amounts are a **symbolic stake/fee** (paper trading), not realized PnL.
- Discovery-sourced markets carry a generic category label; the engine supports per-category
  calibration once real-money categories are enabled (see `prd.md` §5.6).
- The live link requires the API to be hosted/tunnelled; the seeded replays + verify work
  self-contained.
