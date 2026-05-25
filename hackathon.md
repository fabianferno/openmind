# Agora Agents Hackathon — Canteen × Circle

> **Where AI agents make markets.** A builder series for agents that trade, invest, create, and interface with markets — settled instantly on Arc with USDC.
>
> Source: https://agora.thecanteenapp.com

---

## ⏰ Key Logistics

| | |
|---|---|
| **Format** | Online · 2 weeks |
| **Dates** | May 11 → **May 25, 11:59 PM ET** (deadline) |
| **Settlement** | Arc · USDC |
| **Access** | Apply to join |
| **Final delivery** | Asynchronous — **no live demo day**. Judges review after the deadline. |
| **Submission form** | https://forms.gle/ok3Gr9zhmHnApvK48 |
| **Luma registration** | https://luma.com/7i50p2r9 (passphrase: `SITEx1313`) |

> Note: 11:59 PM ET on May 25 ≈ ~9:30 AM IST on May 26.

---

## Hosts & Partners

- **Canteen (Host)** — A research and technology firm operating at the intersection of crypto, AI, and payments. Hosts and curates the hackathon.
- **Circle (NYSE: CRCL) — Platform** — Global fintech building the largest stablecoin network. Issuer of USDC and EURC.
- **Arc (Settlement)** — Circle's purpose-built L1 blockchain; the "Economic OS for the internet" where capital, humans, and machines coordinate.

**Why Arc matters technically:**
- Sub-second deterministic finality — trades settle instantly and irreversibly (no reorgs).
- **~$0.01 transaction fees, paid in USDC** (not volatile gas tokens) — makes high-frequency, low-margin strategies economical on-chain.

---

## Getting Started (4 steps)

1. **Join the Canteen Discord** — https://discord.gg/TGnyfKh23V — introduce yourself.
2. **Join the Arc builder Discord** — https://discord.com/invite/buildonarc — **mention "Canteen + Agora"** in onboarding. If rejected, ping **@aadi** in the Canteen Discord.
3. **Install the ARC CLI:**
   ```
   uv tool install git+https://github.com/the-canteen-dev/ARC-cli
   ```
   Includes RPC access to a Canteen-hosted Arc testnet, plus Arc repos/docs pre-bundled as agent context. Docs: https://arc-node.thecanteenapp.com/
4. **Submit your project** — https://forms.gle/ok3Gr9zhmHnApvK48
   - Required: public GitHub repo link + recorded video demo (≤3 min recommended).
   - Optional but strongly encouraged: live deployed link.
   - Traction questions asked (users onboarded, problems solved).
   - Submit as many times as you like.

---

## Awards — $50k total

| Tier | Amount | Detail |
|---|---|---|
| **Grand Prizes** | **$40k** | 1st: $10k (1 team) · 2nd: $7.5k × 2 teams ($15k) · 3rd: $5k × 3 teams ($15k) |
| **Standout Teams** | **$7.5k** | 10–12 teams in ~equal shares (~$650–$750 each); not ranked |
| **Feedback Incentives** | **$500** | Best product feedback on Circle's developer tooling |
| **Easter Eggs** | **$2k** | Code-golf, Discord puzzles, content challenges, side quests |

*Paid in cash or equivalent.*

---

## Judging Criteria

> "We weigh **agency and traction equally.**" Weightings are recommendations — judges have final say.

| Weight | Criterion | What it means |
|---|---|---|
| **30%** | Agentic Sophistication | How much the AI actually *decides* vs. just automates. Full autonomy > meaningful agency > AI-flavored automation. |
| **30%** | Traction | Real users, real transactions, real volume during the 2-week window. |
| **20%** | Circle tool usage | Creative/effective use of Wallets, CCTP, Gateway, App Kit, Contracts, USYC, USDC. |
| **20%** | Innovation | Novel approaches, emergent behavior, research insight. |

**Judges:** panel with backgrounds from Solana, Coinbase, Arc/Circle, and Protocol Labs. They read repos "like operators, not spectators."

**Each submission includes:**
- Video demo (Loom/YouTube/Vimeo, ≤3 min) — **required**
- Live product link — encouraged
- Public GitHub repo — **required**
- Written traction report — part of the submission, not an afterthought.

---

## The Stack (Circle developer platform on Arc)

**Docs:** Arc — https://docs.arc.network/ · Circle — https://developers.circle.com/

| Product | What it does | Hackathon use case |
|---|---|---|
| **CCTP** (Cross-Chain Transfer Protocol) | Move USDC between chains | Cross-chain arbitrage execution, multi-venue collateral rebalancing |
| **Gateway** | Unified USDC balance across chains, sub-500ms transfers | Single-balance agents acting on any chain instantly |
| ↳ **Nanopayments** | Gas-free USDC payments as small as $0.000001 via batched txns | High-frequency agentic commerce |
| **Wallets** | Embed secure wallets in any app | Trading/betting accounts with automated key management for agents |
| **Contracts** | Build/manage smart contracts | Position management, liquidation protection, hedging logic |
| **Paymaster** | Pay transaction fees in USDC | User-facing agent UX, all costs in USDC |
| **USYC** | Tokenized money market fund | Park idle capital in yield; risk-off allocation |
| **USDC & EURC** | Leading digital dollar & euro | Native settlement, multi-currency/FX-aware strategies |
| **App Kit** | Drop-in components: Bridge, Swap, Send, Unified Balance | Common flows in a few lines of code |

**Reference sample apps (open source):**
- `arc-commerce` — USDC payments for credit purchases
- `arc-multichain-wallet` — unified USDC balance + crosschain transfers
- `arc-escrow` — AI-powered work validation + USDC settlement
- `arc-fintech` — multichain treasury with crosschain capital movement
- `arc-p2p-payments` — gasless P2P payments on Arc

Index: https://docs.arc.network/arc/references/sample-applications

---

## Requests for Builders (RFBs)

> Six open problems — **not tracks**. You don't need to work on any of these to participate. "The best submissions are always what you care most about."

### RFB 01 — Perpetual Futures Trading Agent
24/7 monitoring, split-second leverage decisions, autonomous liquidation protection.

**Architecture (read first):** Two-layer build, kept separate. **Arc has no native perp matching engine** — do not route/match orders on Arc.
- **Execution venue (off-Arc):** open/manage/close positions on a liquid perp venue (Hyperliquid, dYdX, GMX, Vertex). Matching, leverage, liquidation happen here.
- **Arc (settlement/accountability):** collateral movement (CCTP), anchors decisions/fills/PnL on-chain, holds the verifiable track record.

**AI decides:** when to open/close leveraged positions; optimal leverage (2x vs 10x); dynamic stop-loss/take-profit; funding-rate arb across venues; automated liquidation protection.
**Example builds:** PerpAI, SafeLeverage, FundingFarmer.
**Traction metrics:** active traders, trading volume, PnL/Sharpe, AUM.

### RFB 02 — Prediction Market Trader Intelligence
Find +EV bets across noisy news/data/sentiment; size positions properly.

**AI decides:** mispriced markets via data analysis; optimal bet sizing (Kelly or alternatives); when to hedge/close early; portfolio construction across correlated markets; source credibility weighting.
**Example builds:** InsightAgent, PredictPortfolio, ArbitrageOracle.
**Traction metrics:** active users, prediction accuracy, volume wagered, documented returns.

### RFB 03 — Prediction Market Verticals
Launch markets that should exist but don't.

**Builders create:** macroeconomic (CPI, Fed, jobs, GDP), geopolitical (elections, conflicts, trade), institutional hedging tools, multi-currency settlement (EURC/USDC), internal corporate forecasting markets, market-creation tools with auto-liquidity, oracle integrations, forex (USDC↔EURC) markets.
**Example builds:** MacroOracle, EventHedge, CorpForecast.
**Traction metrics:** markets created, liquidity provided, resolution accuracy, volume per market.

### RFB 04 — Adaptive Portfolio Manager
Constant rebalancing, regime detection, tax optimization — cross-chain.

**AI decides:** allocation by regime (risk-on/off); rebalance vs. let winners run; yield allocation (park in USYC during risk-off); tax-loss harvesting; correlation-based diversification (DeFi + TradFi); exposure reduction in high vol.
**Example builds:** AdaptiveFolio, TaxOptimizer, RegimeShift.
**Traction metrics:** users, AUM, returns vs benchmark (BTC, S&P 500), turnover/rebalancing frequency.

### RFB 05 — Cross-Platform Arbitrage Agent
Detect, route, execute — survive slippage.

**AI decides:** when real arb exists; trade sizing for slippage/fees; which bridge/route (CCTP vs alternatives); profitability after costs; risk if price moves mid-execution.
**Example builds:** ArbAgent, TriangularArb, FundingArb.
**Traction metrics:** opportunities captured, total profit, avg execution time, success rate.

### RFB 06 — Social Trading Intelligence
AI selects, weights, and monitors traders to copy (vs. blind mirroring).

**AI decides:** which traders to follow (risk-adjusted returns); capital allocation per trader; when to stop following (strategy degradation); portfolio across signal sources; signal-quality filtering.
**Example builds:** SmartMirror, SignalAggregator, CopyProtect.
**Traction metrics:** leaders/followers, assets copy-traded, performance vs leader, follower retention.

---

## Research — buildable angles

Hosts' own list of "hacks" where Arc's cheap fees + sub-second finality unlock something new. (Canteen's prediction-market analysis: https://thecanteenapp.com/analysis/2026/05/01/unbundling-the-prediction-market-stack.html)

1. **Trading-R1 — reasoning traces as the product.** The value is the *reasoning trace, not the trade*. Hash + pin traces (IPFS/Irys, hash on Arc) cheaply → new market type: bets on which reasoning patterns converge to profit. *Ties to RFB 06.* (arxiv.org/abs/2509.11420)
2. **Builder codes as the agent monetization layer (Polymarket V2).** An agent that *recommends* a bet takes a cut of every fill from its recommendation — no custody, on-chain attribution. Thin "agent-as-builder" wrapper earns USDC builder fees per fill. *Ties to RFB 02 — the real answer to "how does it make money."* (docs.polymarket.com/trading/clients/builder)
3. **Freqtrade blacklist as a tradable oracle.** NostalgiaForInfinity commits = real-time rugpull detection with a public log. Parse the feed, mint each blacklist add as a signed Arc event, seed "will [coin] lose >50% in 7 days" markets. Sub-second finality lets the market open in the same block the signal lands. *Ties to RFB 03.* (github.com/iterativv/NostalgiaForInfinity)
4. **Translation as alpha.** TradingAgents frameworks are interchangeable; the translation layer is the moat. A market where agents bid USDC for the right to translate a non-English news event into a Polymarket-shaped question, builder fees flowing to translators per fill. *Ties to RFB 03.* (arxiv.org/pdf/2412.20138)
5. **Hyperliquid whale cross-migration index token.** An Arc-native ERC-20 holding USDC that auto-rebalances across HL forks based on top-trader migration; each rebalance is a Gateway cross-chain move costing cents. *Ties to RFB 04 & 06.* (hyperliquid.gitbook.io/hyperliquid-docs/historical-data)
6. **Slash-bonded leaderboard copy-trading.** A USDC performance bond on a whale; a contract reads leaderboard rank via oracle and slashes proportionally (settling in <1s) if the leader decays below threshold. *Ties to RFB 06.* (docs.nansen.ai/api/hyperliquid/hyperliquid-leaderboard)

---

## Quick Links

- Site: https://agora.thecanteenapp.com
- Submit: https://forms.gle/ok3Gr9zhmHnApvK48
- Register (Luma): https://luma.com/7i50p2r9 — passphrase `SITEx1313`
- Canteen Discord: https://discord.gg/TGnyfKh23V
- Arc builder Discord: https://discord.com/invite/buildonarc
- ARC CLI: `uv tool install git+https://github.com/the-canteen-dev/ARC-cli`
- ARC node docs: https://arc-node.thecanteenapp.com/
- Arc docs: https://docs.arc.network/ · Circle docs: https://developers.circle.com/

*Agora Agents Hackathon · Canteen × Circle · 2026*