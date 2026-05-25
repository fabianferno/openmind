# openmind — Hackathon Submission

**The prediction-market agent that shows its work — and proves it on-chain.**

- **Live app:** https://openthemind.vercel.app
- **Repo:** https://github.com/fabianferno/openclob
- **Track:** Agora Agents Hackathon (Canteen × Circle) — RFB 02 *Prediction Market Trader Intelligence* + research angle #1 *"reasoning traces as the product, anchored on Arc."*

---

## Problem Statement*

> *What problem is your project solving? What is compelling about this problem?*

AI trading agents are black boxes. They emit a number — "bet YES at 62%" — and ask you to trust it. On prediction markets that's fatal, because the edge doesn't come from price action; it comes from **synthesis of messy public information**. You can't trust — or improve — reasoning you can't inspect, and nothing today ties an agent's *claimed* reasoning to the trade it actually placed. A confident number is indistinguishable from a hallucinated one.

What's compelling is that prediction markets are the cleanest possible testbed for verifiable machine reasoning: every market resolves to a ground truth, so a reasoning trace is either calibrated or it isn't — there's no hiding. If you can make an agent's *thinking* a first-class, auditable, tamper-evident artifact, you turn "trust me" into "verify me." That's the difference between a random polymarket trading agent on twitter and an accountable autonomous system — and it's a primitive that matters far beyond trading (any agent that takes consequential actions should be able to prove *why*).

---

## Project Description*

> *Describe what your project does, how it works, and what tech you used.*

openmind makes the reasoning the product, not the number. For each prediction market it:

1. Builds a knowledge graph (GraphRAG). It designs a custom ontology—the entity and relationship types that matter for this market—then extracts an entity knowledge graph from date-bounded news. A temporal_guard drops any source published after the market's reasoning cutoff, so backtests and live runs can't cheat with hindsight. The graph summary is added to the forecast prompt and directly drives the decision; remove it, and the decision changes.
2. Decides like a calibrated trader. It estimates probability of YES, computes the edge versus market price, sizes the trade using fractional Kelly (per-category calibration), and executes—constrained by hard circuit breakers that the language model cannot bypass (such as daily loss cap, max open positions, per-market cap, slippage guard).
3. Proves it on Arc. It makes the full reasoning trace (ontology, graph, evidence, decision) canonical, hashes it (sha256), anchors the hash on Arc, and settles a symbolic USDC stake. Anyone can re-hash the trace in their browser at /verify/<id> and confirm it matches the chain—a glass box, not a black box.
4. Lets users sign it themselves. A header toggle switches between demo mode (server wallet signs) and personal mode. In personal mode, users log in, get an embedded wallet on Arc (Privy, no seed phrase), top up from the Circle USDC faucet, and sign the anchor and USDC settlement from their own wallet in-browser. Gas is paid in USDC; the server never holds the user's key.

How it works (pipeline): discovery → cheap filters → ambiguity check → date-bounded Tavily search (with temporal guard) → GraphRAG (ontology, entities, graph) → graph-augmented reasoning → calibrated Kelly sizing → paper/dry-run execution → on-chain anchor and USDC settlement on Arc. It runs fully autonomously via /api/auto or agent cycle/loop—no human picks the markets.

Tech: Python swarm inference engine (openclob) with Amazon Nova Lite via AWS Bedrock for reasoning (about $0.015 per full analysis, about $0.008 per decision), Tavily for date-bounded search, FastAPI sidecar streaming the live build over server-sent events (SSE), web3.py to Arc testnet (EVM, chain id 5042002, gas in USDC), SQLite and MongoDB for graph runs, trace blobs, and on-chain anchors. The frontend is Next.js, Tailwind, and shadcn-style components (Terminal, Reasoning Room, Verify, Ledger). Personal mode uses Privy embedded wallets and the Circle faucet, with a client-signed ERC-20 USDC settlement.

---

## Traction*

> *How many real people have tried the product? How much validation from end users? RTs / follows / stars too =)*

We're honest here: this is a final-window build, so our traction is **real on-chain volume, not an organic user base** — and every number is independently verifiable, not a screenshot.

40 real Arc testnet transactions produced by the agent during the hackathon: 30 reasoning-trace anchors and 10 USDC settlements (about 0.10 USDC total), across 26 distinct markets and 30 autonomous decisions. The full list with arcscan links is in TRACTION.md. Agent wallet: 0x5a09e3eC3EFDD91205Cbb097142a4f4dCEFc7f02.

Total LLM spend to produce all of it: $0.25 (Amazon Nova).

There is a live deployed app at https://openthemind.vercel.app and a public repo which anyone can run end-to-end. Running "python -m tools.traction_run 25" reproduces real Arc transactions.

Personal mode turns judges and visitors into the traction: anyone can log in, get an embedded Arc wallet, fund from the Circle faucet, and produce their own verifiable on-chain decision, which is attributed to them in the ledger.

What we don't have yet: a real external user base or wagered volume, and we won't dress up agent-generated activity as organic growth. The path to organic traction is concrete: agent-as-builder USDC fees on recommended fills, a public "verified reasoning" feed, and markets on which reasoning patterns convert to profit.

*(Social: please fill in current GitHub stars / RTs / follows at submission time — e.g. "⭐ N stars, M RTs on the demo thread.")*

---

## Arc OSS — Why choose us / what primitives we expose

> *Why should we choose your project for Arc OSS? What primitives are you exposing that other builders could find useful? Compared to the existing Arc builder code (mostly `circlefin/arc-*`), what tools and flows do you add?*

Most Arc example code shows payments and transfers. openmind adds a different, reusable primitive: verifiable agent-reasoning anchored on Arc, settled in USDC. This turns Arc into a proof-of-reasoning layer, not just a payment rail. The reason Arc is needed is economic: anchoring an entire reasoning trace costs about $0.01 in USDC thanks to sub-cent fees, instant finality, and gas paid in USDC. On a typical L1, anchoring would cost more than the trade itself, so the whole "prove every decision" pattern only makes sense on Arc.

Primitives we expose (usable as drop-in tools for other builders):

- agent/onchain/trace.py — canonical trace and hash, implemented as pure functions with no web3 or database dependencies. build_trace(), canonical(), and trace_hash() take any structured agent output and produce deterministic canonical bytes and a sha256 hash. Any agent can reuse these for tamper-evident, re-hashable output, not just trading agents.
- agent/onchain/arc.py — ArcClient, based on web3.py. This is a minimal Arc client that exposes two core operations: anchor(hash), which writes a 32-byte hash as transaction calldata, and transfer_usdc(to, amount), which settles on ERC-20 USDC with 6-decimal handling built in. It also supports usdc_balance(). The client degrades gracefully to clearly-flagged mock transactions when ARC_ENABLED is false, the key is missing, or RPC fails, so demos and CI never get blocked by faucet or RPC errors. This mock-fallback pattern is itself a useful ergonomic for Arc-based builders.
- Client-side verify flow. GET /api/trace/{id} returns the exact canonical bytes and on-chain anchors; the browser re-hashes and compares to the chain at /verify/<id>. This is a copy-pasteable pattern for proving an off-chain artifact matches an on-chain anchor.
- Bring-your-own-wallet agent flow. In personal mode, a user gets an embedded wallet on Arc (using Privy), onboards through the Circle USDC faucet, and signs the anchor and ERC-20 USDC settlement themselves. Gas is in USDC and there is no custody. This is a complete reference for letting a user, instead of the server key, sign an agent's on-chain action.

The flows we add beyond circlefin/arc-* are: (1) hash-anchoring arbitrary agent output as a first-class action; (2) an off-chain to on-chain verification round-trip; (3) a mock-or-real Arc client that keeps non-funded environments working; (4) a faucet-onboarded, user-signed settlement flow wired to an embedded wallet. Honest note: embedded wallets are implemented via Privy for fastest shipping during the hackathon window, not the Circle Wallets SDK—using the SDK would be a drop-in next step, and USYC treasury yield is a documented future stretch.

---

## Circle / Arc Feedback

What worked

- Gas paid in USDC, with sub-cent transaction fees and instant finality, made a huge difference for us. We were only able to anchor every reasoning trace because Arc's fee model makes it economically viable—it's the clearest thing Arc enables that we couldn't do elsewhere. Not having to deal with a separate gas token made onboarding dramatically easier.
- EVM compatibility meant we could use `web3.py` immediately and without issues. Our `ArcClient` is a simple wrapper; using the standard ERC-20 ABI for USDC and regular transaction construction meant almost no learning curve for anyone already familiar with EVM chains.
- The Circle faucet on Arc Testnet (faucet.circle.com) made onboarding straightforward: just select the chain, fund the wallet, and you're done. This enables a seamless personal mode demo for anyone.
- arcscan gave our traction real credibility. Having a link to a verifiable transaction for each decision lets judges check the validity themselves, rather than taking our word for it.

Where Circle / Arc can improve

- Onboarding into Circle Wallets was slower than we hoped. We ended up using Privy because we could deploy embedded wallets faster in the hackathon timeframe. A clear, ready-to-go quickstart or Next.js demo for Circle Wallets (letting users log in, set up a wallet, and send their first USDC transaction in minutes) would make a big difference. The main friction was the user signing from their own Circle wallet, not the chain itself.
- It's hard to find canonical example repos that show more advanced use cases. The `circlefin/arc-*` repositories mostly cover payments and transfers. An example of anchoring arbitrary calldata or hashes (and how to verify them off-chain and on-chain) would have saved us quite a bit of trial and error figuring out the transaction format.
- Reliability of the testnet RPC could improve, especially when sending multiple transactions at once. We encountered a nonce race during our concurrent runs (though our mock fallback handled it gracefully). Clearer guidance about nonce management and any rate limits would help builders running agent-like workloads with many transactions.
- More documentation for USYC and treasury-yield options would help. We wanted to use idle USDC for yield, but couldn't find a straightforward way to do so within the hackathon window, so we left it as a future enhancement. A simple builder guide or recipe for "how to earn yield on idle USDC" would be very useful.

---

## General Feedback

> *What worked well? What didn't? What could the Canteen team improve for future hackathons?*

What worked well

- The RFB framing and research angle prompts were clear and inspiring. The idea of "reasoning traces as the product, anchored on Arc" provided a strong, specific direction while still leaving room for creativity. This was much more effective than a generic "build on X" assignment.
- Judges who really understood repos and prioritized agency and traction set the right tone for the hackathon. This pushed us to build a real, functioning system with actual safeguards—instead of mere mockups or slideware—and to be transparent about what was fully developed vs. still in progress.
- Having a clear pairing between Canteen and Circle, with a specific chain to target, kept the scope focused and actionable.

What was harder or could be improved

- Achieving visible traction is naturally difficult for projects built in the short final window, especially when the rubric places so much weight (30%) on it. It might be better to also recognize verifiable on-chain activity or a reproducible automated pipeline as meaningful traction, rather than expecting organic user growth in 48 hours—which may lead some teams to inflate their stats.
- Earlier and clearer sponsor tooling quickstarts would help. A short, direct "golden path" for each sponsor (outlining the key SDKs and a working example snippet) at kickoff would allow teams to spend more time on product and less time figuring out libraries and dependencies.
- Setting expectations for reporting or traction-logging up front (like a standard arc-canteen update convention) would be valuable. We only learned about the cadence late, and knowing earlier would have made tracking and reporting traction a smoother process.

Overall, this was a very well-organized hackathon that encouraged building real products, not just demos. Thank you.

---

*Built on [`openclob`](./prd.md) — a phased autonomous prediction-market trading engine (backtest → paper → dryrun → live), gated on Brier/ECE/ROI before real money. See [`pitch.md`](./pitch.md) and [`TRACTION.md`](./TRACTION.md) for the full story and verifiable numbers.*
