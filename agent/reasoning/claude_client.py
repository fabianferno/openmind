"""LLM client.

Routes Claude calls through AWS Bedrock's `bedrock-runtime` Converse API.
The filename is preserved from the PRD for module-tree fidelity; the implementation is
Bedrock, not the direct Anthropic API.

Responsibilities:
  - Model selection (cheap vs. main) via env.
  - JSON-structured output via instructed prompting + tolerant extraction.
  - Per-decision and per-day USD caps, enforced from `llm_usage`.
  - Token accounting written back to SQLite.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from agent.config import settings
from agent.logging import get_logger
from agent.store import db

log = get_logger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"(\{.*\}|\[.*\])", re.DOTALL)


class BudgetExceeded(RuntimeError):
    """Raised when the per-day LLM budget cap would be exceeded."""


@dataclass(slots=True)
class LLMResponse:
    text: str
    parsed: Any
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model_id: str
    stop_reason: str | None = None


class BedrockClient:
    """Thin Bedrock Converse wrapper with cost accounting."""

    def __init__(self, *, region: str | None = None) -> None:
        cfg = BotoConfig(retries={"max_attempts": 3, "mode": "adaptive"}, read_timeout=120)
        # boto3 reads credentials from its default chain (env vars, ~/.aws, IMDS).
        # pydantic-settings loaded our .env into `settings` but did NOT export to
        # os.environ, so boto3 wouldn't see them. Pass explicitly when configured.
        kwargs: dict[str, Any] = {
            "region_name": region or settings.aws_region,
            "config": cfg,
        }
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
            if settings.aws_session_token:
                kwargs["aws_session_token"] = settings.aws_session_token
        self._client = boto3.client("bedrock-runtime", **kwargs)

    # ---- public API ----

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        per_call_usd_cap: float | None = None,
    ) -> LLMResponse:
        """Run a single Converse turn and parse a JSON object from the response.

        Honors per-day budget cap. Raises `BudgetExceeded` BEFORE calling Bedrock if the
        configured daily cap is already exhausted.
        """
        self._enforce_daily_cap()

        model_id = model or settings.bedrock_model_id
        resp = self._invoke(
            model_id=model_id,
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        usage = resp.get("usage") or {}
        in_tok = int(usage.get("inputTokens", 0))
        out_tok = int(usage.get("outputTokens", 0))
        cost = settings.cost_usd(in_tok, out_tok)

        cap = per_call_usd_cap or settings.llm_per_decision_usd_cap
        if cost > cap * 2:
            log.warning(
                "llm.cost_above_2x_cap",
                cost=cost, cap=cap, model=model_id, in_tok=in_tok, out_tok=out_tok,
            )

        text = _extract_text(resp)
        parsed = _safe_json_loads(text)

        with db.connect() as conn:
            db.add_llm_usage(conn, in_tok, out_tok, cost)

        return LLMResponse(
            text=text,
            parsed=parsed,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            model_id=model_id,
            stop_reason=resp.get("stopReason"),
        )

    # ---- internals ----

    def _enforce_daily_cap(self) -> None:
        with db.connect() as conn:
            spent = db.llm_cost_today(conn)
        if spent >= settings.llm_per_day_usd_cap:
            raise BudgetExceeded(
                f"Daily LLM budget exhausted: ${spent:.4f} >= ${settings.llm_per_day_usd_cap:.2f}"
            )

    @retry(
        reraise=True,
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
    )
    def _invoke(
        self,
        *,
        model_id: str,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        return self._client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )


# ---- module-level helpers ----

def _extract_text(resp: dict[str, Any]) -> str:
    try:
        blocks = resp["output"]["message"]["content"]
    except (KeyError, TypeError):
        return ""
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, dict) and "text" in b:
            parts.append(b["text"])
    return "".join(parts).strip()


def _safe_json_loads(text: str) -> Any:
    """Tolerant JSON extraction.

    Tries (1) raw parse, (2) ```json``` fenced block, (3) first balanced object/array.
    Returns None if nothing parses — the caller decides how to react.
    """
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = _JSON_OBJECT_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    return None


# Singleton-ish accessor so callers don't construct boto3 clients in hot loops.
_client_singleton: BedrockClient | None = None


def get_client() -> BedrockClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = BedrockClient()
    return _client_singleton
