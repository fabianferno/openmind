"""Prompt builders + structured-output schemas.

Three call types (§8.1 of the PRD):

  1. ambiguity_check — cheap pre-filter. Goal: reject markets whose resolution criterion
     can't be objectively determined from public information.
  2. entry_reasoning — full forecast. Returns {p_yes, confidence, rationale, key_signals,
     edge_vs_market, recommended_action}.
  3. exit_reasoning — re-evaluates an open position. Returns {action, p_yes, rationale}.

All prompts pin the agent to `as_of` and instruct it to ignore post-dated content.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# ---------- system prompts ----------

AMBIGUITY_SYSTEM = (
    "You are a strict resolution-criterion auditor for prediction markets. "
    "Your job is to decide whether a market's resolution criterion is objectively, "
    "unambiguously determinable from public information by the stated resolution date. "
    "You reject anything that depends on subjective UMA-style phrasing like 'officially', "
    "'credibly', 'by [vague date]' unless the wording is tight. "
    "Reply only with valid JSON matching the requested schema."
)

ENTRY_SYSTEM = (
    "You are a calibrated forecaster trading prediction markets. "
    "You estimate P(YES) for the stated market AS OF the supplied timestamp, "
    "using ONLY information dated on or before that timestamp. "
    "You ignore any content that appears to post-date the as-of timestamp, even if it "
    "is in the provided search results. "
    "You are honest about uncertainty — most markets are correctly priced. "
    "You cite specific evidence by URL and date when justifying your estimate. "
    "You reply only with valid JSON matching the requested schema."
)

EXIT_SYSTEM = (
    "You are a calibrated forecaster managing an OPEN position in a prediction market. "
    "Given the entry decision, current market state, and new evidence, you decide whether "
    "to hold, take profit, stop out, scale in, or scale out. "
    "You ignore any content dated after the as-of timestamp. "
    "You reply only with valid JSON matching the requested schema."
)


# ---------- user prompts ----------

def build_ambiguity_prompt(market: dict[str, Any]) -> str:
    return f"""Market: {market["question"]}

Resolution rules:
{market.get("resolution_rules") or "(none provided)"}

Resolution source: {market.get("resolution_source") or "(unspecified)"}
End date: {market.get("end_date") or "(unspecified)"}

Decide whether the resolution outcome is unambiguously determinable from public information
by the end date. Subjective phrasing (officially, credibly, by [vague date], etc.) without
tight scoping is grounds for rejection.

Respond in this exact JSON shape:
{{
  "unambiguous": true | false,
  "rationale": "<one sentence>"
}}"""


def _format_search(results: list[dict[str, Any]]) -> str:
    if not results:
        return "(no usable date-bounded search results)"
    lines = []
    for i, r in enumerate(results, start=1):
        date = r.get("published_date") or "undated"
        title = (r.get("title") or "")[:120]
        url = r.get("url") or ""
        content = (r.get("content") or "")[:600].replace("\n", " ")
        lines.append(f"[{i}] ({date}) {title}\n    {url}\n    {content}")
    return "\n".join(lines)


def build_entry_prompt(
    market: dict[str, Any],
    *,
    as_of: datetime,
    market_price_yes: float,
    search_results: list[dict[str, Any]],
    graph_summary: str | None = None,
) -> str:
    graph_block = (
        f"\nKNOWLEDGE GRAPH (entities & relationships extracted from the evidence below — "
        f"use it to reason about who/what drives this market):\n{graph_summary}\n"
        if graph_summary else ""
    )
    return f"""AS OF: {as_of.isoformat()}

Market: {market["question"]}
Category: {market.get("category") or "unspecified"}
End date: {market.get("end_date") or "unknown"}
Resolution rules:
{market.get("resolution_rules") or "(none)"}

Current market price for YES: {market_price_yes:.3f}
{graph_block}
DATE-BOUNDED EVIDENCE (do NOT use any content dated after {as_of.date().isoformat()}):
{_format_search(search_results)}

Tasks:
1. Estimate P(YES) given only the evidence above.
2. State your confidence (0-1) in that estimate. Calibration matters more than boldness.
3. Identify the key signals that drove the estimate.
4. Compute the edge versus market price: edge = p_yes - market_price_yes (for YES side; use
   negative if you'd take NO).
5. Recommend one of: 'enter_yes', 'enter_no', 'skip'.
   - Recommend a side only if |edge| >= 0.05 AND your confidence >= 0.5.

Respond in this exact JSON shape:
{{
  "p_yes": <float 0..1>,
  "confidence": <float 0..1>,
  "rationale": "<3-6 sentences>",
  "key_signals": ["<short bullet>", ...],
  "edge_vs_market": <float>,
  "recommended_action": "enter_yes" | "enter_no" | "skip"
}}"""


def build_exit_prompt(
    market: dict[str, Any],
    *,
    as_of: datetime,
    position: dict[str, Any],
    current_price_yes: float,
    prior_p_yes: float | None,
    search_results: list[dict[str, Any]],
) -> str:
    side = position["side"]
    entry_price = position["entry_price"]
    shares = position["shares"]
    pnl_unrealized = (current_price_yes - entry_price) * shares if side == "YES" else (
        (1 - current_price_yes) - (1 - entry_price)
    ) * shares
    return f"""AS OF: {as_of.isoformat()}

Open position:
  market: {market["question"]}
  side: {side}
  shares: {shares:.4f}
  entry price: {entry_price:.3f}
  current YES price: {current_price_yes:.3f}
  prior p_yes estimate: {prior_p_yes if prior_p_yes is not None else "n/a"}
  unrealized PnL (USD-equivalent): {pnl_unrealized:.3f}

Resolution rules:
{market.get("resolution_rules") or "(none)"}

NEW DATE-BOUNDED EVIDENCE (ignore anything dated after {as_of.date().isoformat()}):
{_format_search(search_results)}

Decide:
  - 'hold': thesis intact, no edge to act on now.
  - 'take_profit': close (or scale out) because price has converged to fair.
  - 'stop_loss': close because thesis is broken or new evidence flipped it.
  - 'scale_in': add to position because edge has widened.
  - 'scale_out': trim because conviction softened but thesis still holds.

Respond in this exact JSON shape:
{{
  "action": "hold" | "take_profit" | "stop_loss" | "scale_in" | "scale_out",
  "p_yes": <float 0..1>,
  "rationale": "<2-5 sentences>",
  "size_fraction": <float 0..1>     // fraction of remaining position to act on; 1.0 for full close
}}"""


# ---------- structured output validation ----------

def validate_ambiguity(parsed: Any) -> dict[str, Any] | None:
    if not isinstance(parsed, dict):
        return None
    if not isinstance(parsed.get("unambiguous"), bool):
        return None
    return {
        "unambiguous": parsed["unambiguous"],
        "rationale": str(parsed.get("rationale", ""))[:1000],
    }


def validate_entry(parsed: Any) -> dict[str, Any] | None:
    if not isinstance(parsed, dict):
        return None
    try:
        p_yes = float(parsed["p_yes"])
        conf = float(parsed["confidence"])
        edge = float(parsed["edge_vs_market"])
    except (KeyError, TypeError, ValueError):
        return None
    action = parsed.get("recommended_action")
    if action not in ("enter_yes", "enter_no", "skip"):
        return None
    if not (0.0 <= p_yes <= 1.0) or not (0.0 <= conf <= 1.0):
        return None
    return {
        "p_yes": p_yes,
        "confidence": conf,
        "rationale": str(parsed.get("rationale", ""))[:3000],
        "key_signals": [str(s)[:300] for s in parsed.get("key_signals", [])][:10],
        "edge_vs_market": edge,
        "recommended_action": action,
    }


def validate_exit(parsed: Any) -> dict[str, Any] | None:
    if not isinstance(parsed, dict):
        return None
    action = parsed.get("action")
    if action not in ("hold", "take_profit", "stop_loss", "scale_in", "scale_out"):
        return None
    try:
        p_yes = float(parsed["p_yes"])
        size_frac = float(parsed.get("size_fraction", 1.0))
    except (KeyError, TypeError, ValueError):
        return None
    if not (0.0 <= p_yes <= 1.0):
        return None
    size_frac = max(0.0, min(1.0, size_frac))
    return {
        "action": action,
        "p_yes": p_yes,
        "rationale": str(parsed.get("rationale", ""))[:3000],
        "size_fraction": size_frac,
    }
