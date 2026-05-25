"""Circuit breakers (PRD §6.3).

Hard-coded, not bypassable by LLM. Each check returns a `BreakerCheck` with `tripped:bool`
and a reason. The agent loop must abort entry placement if any breaker is tripped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agent.config import settings
from agent.logging import get_logger
from agent.store import db

log = get_logger(__name__)

API_FAILURE_THRESHOLD = 3
API_FAILURE_COOLDOWN = timedelta(hours=1)
DAILY_LOSS_COOLDOWN = timedelta(hours=24)


@dataclass(slots=True)
class BreakerCheck:
    name: str
    tripped: bool
    reason: str | None = None


def _expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at)
        return datetime.now(UTC) >= exp
    except ValueError:
        return False


def _check_persisted(name: str) -> BreakerCheck:
    with db.connect() as conn:
        state = db.breaker_status(conn, name)
    if not state or not state["tripped"]:
        return BreakerCheck(name, False)
    if _expired(state.get("expires_at")):
        with db.connect() as conn:
            db.set_breaker(conn, name, tripped=False)
        return BreakerCheck(name, False)
    return BreakerCheck(name, True, state.get("reason") or "tripped")


def check_daily_loss() -> BreakerCheck:
    persisted = _check_persisted("daily_loss")
    if persisted.tripped:
        return persisted
    with db.connect() as conn:
        pnl = db.positions_today_pnl(conn)
    threshold = -settings.agent_daily_loss_cap * settings.agent_bankroll
    if pnl <= threshold:
        expires = (datetime.now(UTC) + DAILY_LOSS_COOLDOWN).isoformat()
        with db.connect() as conn:
            db.set_breaker(
                conn, "daily_loss", tripped=True,
                reason=f"pnl={pnl:.2f} <= threshold={threshold:.2f}",
                expires_at=expires,
            )
        return BreakerCheck("daily_loss", True, f"daily_loss:{pnl:.2f}")
    return BreakerCheck("daily_loss", False)


def check_position_count() -> BreakerCheck:
    with db.connect() as conn:
        n = len(db.open_positions(conn))
    if n >= settings.agent_max_positions:
        return BreakerCheck("position_count", True, f"open={n}>={settings.agent_max_positions}")
    return BreakerCheck("position_count", False)


def check_api_failures() -> BreakerCheck:
    return _check_persisted("api_failures")


def record_api_failure() -> None:
    """Increment API failure count; trip the breaker if past threshold."""
    with db.connect() as conn:
        state = db.breaker_status(conn, "api_failures")
        count = int((state or {}).get("reason", "0").split(":")[-1] or 0) + 1 if state else 1
        if count >= API_FAILURE_THRESHOLD:
            expires = (datetime.now(UTC) + API_FAILURE_COOLDOWN).isoformat()
            db.set_breaker(
                conn, "api_failures", tripped=True,
                reason=f"consecutive_failures:{count}",
                expires_at=expires,
            )
            log.error("breaker.api_failures.tripped", count=count)
        else:
            db.set_breaker(
                conn, "api_failures", tripped=False,
                reason=f"consecutive_failures:{count}",
            )


def record_api_success() -> None:
    with db.connect() as conn:
        db.set_breaker(conn, "api_failures", tripped=False, reason="consecutive_failures:0")


def check_manual() -> BreakerCheck:
    return _check_persisted("manual")


def all_clear() -> tuple[bool, list[BreakerCheck]]:
    """Return (ok, list_of_checks). ok=True iff none are tripped."""
    checks = [
        check_daily_loss(),
        check_position_count(),
        check_api_failures(),
        check_manual(),
    ]
    return all(not c.tripped for c in checks), checks


def slippage_ok(quoted: float, executed: float, *, max_pct: float = 0.02) -> bool:
    if quoted <= 0:
        return False
    return abs(executed - quoted) / quoted <= max_pct


def trip_manual(reason: str) -> None:
    with db.connect() as conn:
        db.set_breaker(conn, "manual", tripped=True, reason=reason)


def reset_manual() -> None:
    with db.connect() as conn:
        db.set_breaker(conn, "manual", tripped=False, reason="cleared")
