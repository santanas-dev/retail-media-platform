"""KSO Player Runtime Gate — safe read-only play/hold decision core.

Reads {root}/state/kso_state.json and decides whether the player is allowed
to show advertising content. The state file is WRITTEN by the external
UKM 4 State Adapter — the player is a READ-ONLY consumer.

Fail-closed: play_allowed=True ONLY when state == "idle", JSON is valid,
timestamp is valid, and state is fresh. All other conditions → hold.

NO backend, NO HTTP, NO auth, NO secret, NO media bytes.
Player NEVER writes kso_state.json.
"""

import json as _json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATE_DIR = "state"
STATE_FILE = "kso_state.json"

# ── Allowed KSO states ──────────────────────────────────────────────

ALLOWED_STATES = frozenset({
    "idle",
    "transaction",
    "payment",
    "receipt",
    "service",
    "error",
    "maintenance",
    "offline",
    "unknown",
})

_IDLE_STATE = "idle"

# ── Actions ─────────────────────────────────────────────────────────

ACTION_PLAY = "play"
ACTION_HOLD = "hold"

# ── Status values ───────────────────────────────────────────────────

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

# ── Reasons ─────────────────────────────────────────────────────────

REASON_PLAY_ALLOWED = "play_allowed"
REASON_MISSING_STATE_FILE = "missing_state_file"
REASON_INVALID_JSON = "invalid_json"
REASON_SCHEMA_MISMATCH = "schema_mismatch"
REASON_INVALID_STATE = "invalid_state"
REASON_MISSING_UPDATED_AT = "missing_updated_at"
REASON_INVALID_UPDATED_AT = "invalid_updated_at"
REASON_STALE_STATE = "stale_state"
REASON_FUTURE_TIMESTAMP = "future_timestamp"
REASON_NON_IDLE_STATE = "non_idle_state"
REASON_READ_FAILED = "read_failed"
REASON_INVALID_ARGS = "invalid_args"

# ── Age buckets ─────────────────────────────────────────────────────

AGE_FRESH = "fresh"
AGE_STALE = "stale"
AGE_UNKNOWN = "unknown"

# ── Forbidden substrings (checked in result/repr/output) ────────────

FORBIDDEN_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
    "backend_base_url", "127.0.0.1", "device_code",
    "filename", "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "full_manifest", "media_bytes", "stacktrace",
    "boot_id", "pid",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoRuntimeGateResult:
    """Safe result of the KSO runtime gate evaluation.

    Never contains absolute paths, file names, raw JSON, timestamps,
    source values, exception text, or forbidden substrings.
    """

    status: str = STATUS_ERROR
    play_allowed: bool = False
    action: str = ACTION_HOLD
    state: str = "unknown"
    state_valid: bool = False
    fresh: bool = False
    reason: str = REASON_INVALID_ARGS
    age_bucket: str = AGE_UNKNOWN
    stale_seconds: int = 0
    age_seconds: int = 0

    def __repr__(self) -> str:
        return (
            f"KsoRuntimeGateResult("
            f"status={self.status!r}, "
            f"play_allowed={self.play_allowed}, "
            f"action={self.action!r}, "
            f"state={self.state!r}, "
            f"state_valid={self.state_valid}, "
            f"fresh={self.fresh}, "
            f"reason={self.reason!r}, "
            f"age_bucket={self.age_bucket!r}, "
            f"stale_seconds={self.stale_seconds}, "
            f"age_seconds={self.age_seconds})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden(value: str) -> bool:
    """Return True if value contains any forbidden substring."""
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return True
    return False


def _parse_iso8601(raw: str) -> Optional[datetime]:
    """Parse an ISO8601 timestamp string into a timezone-aware datetime.

    Supports formats like '2026-06-20T12:00:00Z', '2026-06-20T12:00:00+00:00',
    and '2026-06-20T12:00:00+0300'.

    Returns None if parsing fails. Never raises.
    """
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    try:
        from kso_player.timestamp_utils import parse_iso_utc
        dt = parse_iso_utc(raw)
    except Exception:
        return None
    if dt is None:
        return None

    # Assume UTC (parser returns naive UTC)
    dt = dt.replace(tzinfo=timezone.utc)

    return dt


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def evaluate_kso_runtime_gate(
    root,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
) -> KsoRuntimeGateResult:
    """Evaluate whether the KSO player is allowed to show ads.

    Reads {root}/state/kso_state.json and applies the safety gate:
    - state == "idle" AND valid JSON AND fresh timestamp → play_allowed=true
    - All other cases → hold (fail-closed)

    Player is READ-ONLY — NEVER writes kso_state.json.
    Writer: future UKM 4 State Adapter.

    Args:
        root: Agent root path (str or Path).
        stale_seconds: Maximum age of state before it's considered stale
                       (default: 30 seconds).
        now: Optional datetime for test time injection. Defaults to UTC now.

    Returns:
        KsoRuntimeGateResult — safe aggregate, never raises.
    """
    # ── Validate arguments ───────────────────────────────────────
    if stale_seconds <= 0:
        return KsoRuntimeGateResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
            stale_seconds=stale_seconds,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoRuntimeGateResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
            stale_seconds=stale_seconds,
        )

    if now is None:
        now = datetime.now(timezone.utc)

    state_path = root / STATE_DIR / STATE_FILE

    # ── Read state file ───────────────────────────────────────────
    try:
        raw = state_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            reason=REASON_MISSING_STATE_FILE,
            stale_seconds=stale_seconds,
        )
    except OSError:
        return KsoRuntimeGateResult(
            status=STATUS_ERROR,
            action=ACTION_HOLD,
            reason=REASON_READ_FAILED,
            stale_seconds=stale_seconds,
        )

    # ── Parse JSON ────────────────────────────────────────────────
    try:
        data = _json.loads(raw)
    except (ValueError, TypeError):
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            reason=REASON_INVALID_JSON,
            stale_seconds=stale_seconds,
        )

    if not isinstance(data, dict):
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            reason=REASON_SCHEMA_MISMATCH,
            stale_seconds=stale_seconds,
        )

    # ── Validate state field ──────────────────────────────────────
    raw_state = data.get("state")
    if raw_state is None:
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            reason=REASON_INVALID_STATE,
            stale_seconds=stale_seconds,
        )

    if not isinstance(raw_state, str):
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            reason=REASON_INVALID_STATE,
            stale_seconds=stale_seconds,
        )

    state = raw_state.strip().lower()

    if state not in ALLOWED_STATES:
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            state=state,
            reason=REASON_INVALID_STATE,
            stale_seconds=stale_seconds,
        )

    # ── Validate updated_at_utc field ─────────────────────────────
    raw_updated = data.get("updated_at_utc")
    if raw_updated is None:
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            state=state,
            state_valid=True,
            reason=REASON_MISSING_UPDATED_AT,
            stale_seconds=stale_seconds,
        )

    updated_at = _parse_iso8601(raw_updated)
    if updated_at is None:
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            state=state,
            state_valid=True,
            reason=REASON_INVALID_UPDATED_AT,
            stale_seconds=stale_seconds,
        )

    # ── Check for future timestamp ────────────────────────────────
    if updated_at > now:
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            state=state,
            state_valid=True,
            reason=REASON_FUTURE_TIMESTAMP,
            stale_seconds=stale_seconds,
        )

    # ── Calculate age ─────────────────────────────────────────────
    age_seconds = int((now - updated_at).total_seconds())

    # ── If state is not idle → hold ───────────────────────────────
    if state != _IDLE_STATE:
        if age_seconds > stale_seconds:
            return KsoRuntimeGateResult(
                status=STATUS_WARNING,
                action=ACTION_HOLD,
                state=state,
                state_valid=True,
                fresh=False,
                reason=REASON_NON_IDLE_STATE,
                age_bucket=AGE_STALE,
                stale_seconds=stale_seconds,
                age_seconds=age_seconds,
            )
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            state=state,
            state_valid=True,
            fresh=True,
            reason=REASON_NON_IDLE_STATE,
            age_bucket=AGE_FRESH,
            stale_seconds=stale_seconds,
            age_seconds=age_seconds,
        )

    # ── State is idle — check freshness ───────────────────────────
    if age_seconds > stale_seconds:
        return KsoRuntimeGateResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            state=state,
            state_valid=True,
            fresh=False,
            reason=REASON_STALE_STATE,
            age_bucket=AGE_STALE,
            stale_seconds=stale_seconds,
            age_seconds=age_seconds,
        )

    # ── All checks passed — PLAY ALLOWED ──────────────────────────
    return KsoRuntimeGateResult(
        status=STATUS_OK,
        play_allowed=True,
        action=ACTION_PLAY,
        state=state,
        state_valid=True,
        fresh=True,
        reason=REASON_PLAY_ALLOWED,
        age_bucket=AGE_FRESH,
        stale_seconds=stale_seconds,
        age_seconds=age_seconds,
    )


def format_kso_runtime_gate_result(result: KsoRuntimeGateResult) -> str:
    """Format a KsoRuntimeGateResult as a safe human-readable string.

    Never contains paths, file names, raw JSON, timestamps, source values,
    or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"play_allowed: {str(result.play_allowed).lower()}",
        f"action: {result.action}",
        f"state: {result.state}",
        f"state_valid: {str(result.state_valid).lower()}",
        f"fresh: {str(result.fresh).lower()}",
        f"reason: {result.reason}",
        f"age_bucket: {result.age_bucket}",
        f"stale_seconds: {result.stale_seconds}",
        f"age_seconds: {result.age_seconds}",
    ]
    return "\n".join(lines)
