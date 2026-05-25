"""Persist + load captured analyze event streams for deterministic demo replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEED_DIR = Path("data") / "seeds"


def _path(market_id: str) -> Path:
    safe = market_id.replace("/", "_").replace(":", "_")
    return SEED_DIR / f"{safe}.json"


def save_seed(market_id: str, events: list[dict[str, Any]]) -> Path:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(market_id)
    p.write_text(json.dumps({"market_id": market_id, "events": events}, indent=2))
    return p


def load_seed(market_id: str) -> list[dict[str, Any]] | None:
    p = _path(market_id)
    if not p.exists():
        return None
    return json.loads(p.read_text()).get("events", [])


def list_seeds() -> list[str]:
    if not SEED_DIR.exists():
        return []
    return [p.stem for p in SEED_DIR.glob("*.json")]
