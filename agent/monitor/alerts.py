"""Alerts. Logs to disk always; posts to webhook if configured."""

from __future__ import annotations

import json
from typing import Any

import httpx

from agent.config import settings
from agent.logging import get_logger

log = get_logger(__name__)


def send(level: str, message: str, **fields: Any) -> None:
    payload = {"level": level, "message": message, **fields}
    log.warning("alert", **payload)
    if not settings.alert_webhook_url:
        return
    try:
        body = {"text": f"[{level.upper()}] {message}\n```{json.dumps(fields, default=str)[:1500]}```"}
        httpx.post(settings.alert_webhook_url, json=body, timeout=10.0)
    except httpx.HTTPError as e:
        log.warning("alert.webhook_failed", error=str(e))
