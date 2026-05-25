# openmind — Pitch Kit

**The prediction-market agent that shows its work, and proves it on-chain.**

- **Live app:** https://openthemind.vercel.app
- **Repo:** https://github.com/fabianferno/openclob
- **Track:** Agora Agents Hackathon (Canteen × Circle) — RFB 02 *Prediction Market Trader Intelligence* + research angle #1 *reasoning traces as the product, anchored on Arc*.

---

## 1. The one-liner

> Every trading agent gives you a number. openmind gives you the **reasoning** — a knowledge
> graph it builds from the news to find mispriced markets — and then **anchors that reasoning on
> Arc** so anyone can verify the bet was earned, not hallucinated.

## 2. The problem (say this in 15 seconds)

AI trading agents are black boxes. You see a trade, never the *why*. On prediction markets that's
fatal: edge comes from **synthesis of messy public information**, and you can't trust — or
improve — reasoning you can't inspect. And nothing ties the claimed reasoning to the trade that
was actually placed.

## 3. The solution (30 seconds)

openmind makes the reasoning the product:

1. **Builds a knowledge graph.** For each market it designs a bespoke ontology, then extracts an
   entity graph from *date-bounded* news (leakage-guarded). The graph **feeds the forecast** — it
   drives the decision, it isn't decoration.
2. **Decides like a calibrated trader.** Estimates P(YES), computes edge vs. market price, sizes
   with fractional Kelly, and trades.
3. **Proves it on Arc.** Canonicalises the full reasoning trace, hashes it (sha256), **anchors the
   hash on Arc**, and **settles USDC**. Anyone re-hashes the trace in-browser and matches it to the
   chain. A glass box, not a black box.

Runs on **Amazon Nova** (Bedrock) — a full analysis costs ~**$0.015**.

---

## 4. The 3-minute video script (shot-by-shot)

> Record against the live app or localhost. Use a **seeded** market for the main take (the ▶ replay
> button is deterministic), then show one truly live run. Keep cuts tight.

**[0:00–0:20] — Hook + problem.**
*Screen: the Terminal home page, hero "Reasoning you can verify."*
> "AI agents that trade give you a number and ask you to trust it. openmind is different — it shows
> you exactly how it thinks, and it proves that thinking on-chain. Let me show you."

**[0:20–0:35] — Pick a market.**
*Screen: scroll the live markets grid, click a geopolitical market (e.g. the Ukraine or Iran one).*
> "I'll pick a real prediction market. openmind is going to research it from scratch."

**[0:35–1:30] — The Reasoning Room (THE moment). Hit ▶ run / replay.**
*Screen: left panel — ontology types appear as chips; center — the knowledge graph builds node by
node and wires itself together; right — evidence streams in.*
> "First it designs an ontology — the entity and relationship types that matter for *this* market.
> Then it reads date-bounded news and extracts a knowledge graph, live — people, organizations,
> events, and how they connect. Every node is cited. Nothing published after the cutoff gets in —
> that's the temporal guard that stops it from cheating."

**[1:30–2:05] — The decision.**
*Screen: the decision card fills — P(YES) vs market price bar, edge, Kelly size, rationale.*
> "It reasons *over the graph* to a calibrated probability — here it sees [X]% versus the market's
> [Y]%, an edge of [Z] points — and sizes the position with fractional Kelly. This is real agency:
> it decided what to believe and how much to bet."

**[2:05–2:40] — Settle + anchor on Arc (the proof).**
*Screen: the on-chain panel — USDC settled, trace anchored; click the arcscan link.*
> "Now the part nobody else does. It settles USDC on Arc, and it anchors a hash of the entire
> reasoning trace on-chain — for about a cent, paid in USDC. Here's the real transaction on Arc."

**[2:40–3:00] — Verify + autonomy + close.**
*Screen: Verify page → "✓ Verified" (re-hash matches). Quick cut to the Autonomous page running.*
> "Anyone can re-hash the reasoning in their browser and confirm it matches the chain — verified.
> And it does all of this on its own —" *(show /auto running)* "— picking markets, reasoning, and
> settling, no human in the loop. openmind: reasoning you can verify."

**Fallbacks for the recording:** use ▶ replay (deterministic, no API latency); if the live API is
down, the seeded markets still play the full sequence with their real arcscan links.

---

## 5. Does it fit the rubric? (honest scorecard)

> Judges "weigh agency and traction equally" and "read repos like operators."

| Weight | Criterion | Assessment | Score |
|---|---|---|---|
| **30%** | **Agentic Sophistication** | Strong. Autonomous end-to-end: ontology design → graph extraction → search → graph-driven reasoning → Kelly sizing → execution → on-chain settlement. The `/auto` page and `agent cycle`/`loop` show full autonomy (no human market-pick). | **8.5/10** |
| **30%** | **Traction** | Honest weak spot. Real, quantifiable **on-chain volume on Arc** (dozens of anchored reasoning traces + USDC settlements during the window — see `TRACTION.md`), a live deployed app, and a public repo. What we lack is a real *user* base (final-window build). | **4/10** |
| **20%** | **Circle / Arc tooling** | Solid baseline: real USDC settlement + trace anchoring on Arc testnet, gas paid in USDC, arcscan-verifiable. Stretch (documented, not done): Circle Wallets SDK / USYC treasury yield. | **6.5/10** |
| **20%** | **Innovation** | Strong. Verifiable reasoning traces on-chain is *their own* research angle #1; GraphRAG applied to prediction-market forecasting + the "glass box" thesis is genuinely novel. | **8.5/10** |

**Where we win:** innovation + agency (50% of the score) are our strengths, and they're real, not
slideware. **Where we're capped:** traction — we can't manufacture a user base overnight, so a
*grand* prize is a stretch; a **Standout Team** award and an outside shot at a 3rd-tier grand prize
are the realistic targets.

## 6. Is the product practical / does it make sense?

**Yes — and it's more than a hackathon toy:**

- **Real underlying engine.** It's built on `openclob`, a phased autonomous trading agent with
  leakage-guarded backtesting, calibration tracking, and hard circuit breakers — not a demo shell.
- **The on-chain angle is genuinely useful, not bolted on.** "Reasoning traces as a verifiable
  asset" is a real emerging idea (Trading-R1 / the hosts' own analysis). Anchoring is cheap on Arc
  precisely because of sub-cent USDC fees — the product *needs* Arc's economics to make sense, which
  is exactly the kind of "what does Arc unlock" the hosts asked for.
- **Honest about edge.** The PRD is explicit that this is skill-validation, gated on Brier/ECE/ROI
  before real money. We don't overclaim profitability — judges who read like operators will respect
  that.
- **Clear path to a real product:** agent-as-builder (earn USDC builder fees per recommended fill),
  a public "verified reasoning" feed, and markets *on* which reasoning patterns are most profitable.

**Caveats to own (don't hide them):** the symbolic USDC settlement is a stake/fee, not real PnL
(it's paper trading); the live link depends on the API being hosted; the demo's "pick a market" is
human-initiated while the autonomous loop is the truly hands-off mode.

---

## 7. Anticipated judge questions (prep)

- **"Is the graph real or decoration?"** Real — its summary is injected into the reasoning prompt;
  remove it and the decision changes. See `agent/strategy/entry.py` + `agent/graphrag/`.
- **"What stops data leakage / hindsight?"** A temporal guard drops any source published after the
  market's reasoning cutoff (`agent/reasoning/temporal_guard.py`); there's a dedicated leakage test.
- **"Why Arc specifically?"** Sub-cent USDC fees + instant finality make anchoring every decision
  economical — anchoring on a normal L1 would cost more than the trade. Gas is paid in USDC.
- **"How is this not just an LLM wrapper?"** Ontology design + graph extraction + calibrated Kelly
  sizing + circuit breakers + on-chain settlement is a multi-stage autonomous system; the LLM is one
  component, bounded by hard limits it cannot bypass.
- **"What's the business model?"** Polymarket-style builder codes: the agent earns USDC builder fees
  on fills it recommends — attribution on-chain, no custody.

## 8. Numbers + links to cite

- Model: Amazon Nova (Bedrock) · cost ≈ **$0.015 / full analysis**.
- On-chain: Arc testnet (chain id `5042002`), gas in USDC. Live tx counts in `TRACTION.md`.
- Verify flow: client-side sha256 re-hash matches the on-chain anchor.
- Live app: https://openthemind.vercel.app · Repo: https://github.com/fabianferno/openclob

## 9. Submission checklist

- [x] Public repo
- [x] Live deployed app
- [ ] ≤3-min video (script above)
- [ ] Written traction report (`TRACTION.md` — finalize numbers)
- [ ] `arc-canteen update` logged (traction channel)
- [ ] Submit: https://forms.gle/ok3Gr9zhmHnApvK48
