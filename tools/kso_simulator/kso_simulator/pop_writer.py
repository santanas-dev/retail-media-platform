"""Write PoP events to pop/events.log (JSONL, append-only).

Strictly follows kso_local_interface_contract.md.
This is a DEV TOOL. No secrets, no tokens, no network.
"""

import json
import os
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from kso_simulator import state_writer

# ── Allowed values ──────────────────────────────────────────────────

ALLOWED_RESULTS: frozenset[str] = frozenset({
    "completed",
    "interrupted",
    "skipped",
    "failed",
})

# "completed" requires KSO in idle state
COMPLETED_REQUIRES_IDLE = True

# ── Forbidden substrings in "reason" field ──────────────────────────

FORBIDDEN_REASON_SUBSTRINGS: list[str] = [
    "token",
    "jwt",
    "password",
    "secret",
    "api_key",
    "private_key",
    "local_path",
    "file_path",
    "receipt",
    "payment_card",
    "phone",
    "email",
]


# ── Validation ──────────────────────────────────────────────────────

def _validate_uuid(value: str, field: str) -> str:
    """Raise ValueError if value is not a valid UUID."""
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid {field}: '{value}' is not a valid UUID")
    return value


def _validate_result(result: str) -> str:
    if result not in ALLOWED_RESULTS:
        raise ValueError(
            f"Invalid result '{result}'. Allowed: {', '.join(sorted(ALLOWED_RESULTS))}"
        )
    return result


def _validate_duration_ms(duration_ms: int) -> int:
    if duration_ms < 0:
        raise ValueError(f"duration_ms must be >= 0, got {duration_ms}")
    return duration_ms


def _validate_iso8601(value: str, field: str) -> str:
    """Rudimentary ISO8601 check. Accepts any string that starts with YYYY-MM-DD."""
    if len(value) < 10:
        raise ValueError(f"Invalid {field}: '{value}' too short for ISO8601")
    # Basic sanity: should start with YYYY-MM-DD
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {field}: '{value}' is not valid ISO8601")
    return value


def _validate_reason(reason: Optional[str]) -> None:
    """Reject reason containing forbidden substrings (case-insensitive)."""
    if reason is None:
        return
    lower = reason.lower()
    for forbidden in FORBIDDEN_REASON_SUBSTRINGS:
        if forbidden in lower:
            raise ValueError(
                f"Reason contains forbidden substring '{forbidden}'. "
                f"Forbidden: {', '.join(FORBIDDEN_REASON_SUBSTRINGS)}"
            )


# ── Safety check ────────────────────────────────────────────────────

def _read_kso_state(root: Path) -> dict:
    """Read current kso_status.json. Returns empty dict if not found."""
    status_file = root / "status" / "kso_status.json"
    if not status_file.exists():
        return {}
    try:
        return json.loads(status_file.read_text())
    except json.JSONDecodeError:
        return {}


def _check_safety_for_completed(root: Path) -> None:
    """Raise RuntimeError if 'completed' cannot be written in current state."""
    state_data = _read_kso_state(root)
    state = state_data.get("state", "unknown")
    can_show = state_data.get("can_show_ads", False)

    if state != "idle":
        raise RuntimeError(
            f"Cannot write 'completed' PoP: KSO state is '{state}', "
            f"not 'idle'. Use set-state idle first, or use result='interrupted'/'skipped'/'failed'."
        )
    if not can_show:
        raise RuntimeError(
            "Cannot write 'completed' PoP: can_show_ads=false. "
            "Set state to idle first."
        )


# ── Core write ──────────────────────────────────────────────────────

def write_pop_event(
    root: str | Path,
    *,
    manifest_item_id: str,
    result: str,
    duration_ms: int,
    reason: Optional[str] = None,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> str:
    """Write one PoP event line to pop/events.log (append-only JSONL).

    Returns the device_event_id of the written event.

    Raises:
        ValueError: invalid field value
        RuntimeError: safety check failed (completed requires idle)
    """
    root = Path(root)

    # ── Validate inputs ──────────────────────────────────────────
    _validate_uuid(manifest_item_id, "manifest_item_id")
    _validate_result(result)
    _validate_duration_ms(duration_ms)
    _validate_reason(reason)

    if started_at is not None:
        _validate_iso8601(started_at, "started_at")
    if ended_at is not None:
        _validate_iso8601(ended_at, "ended_at")

    if started_at and ended_at:
        st = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        en = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        if en < st:
            raise ValueError(
                f"ended_at ({ended_at}) must be >= started_at ({started_at})"
            )

    # ── Safety check for 'completed' ─────────────────────────────
    if result == "completed":
        _check_safety_for_completed(root)

    # ── Build timestamps ────────────────────────────────────────
    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"

    event_started = started_at if started_at else now.strftime(fmt)
    event_ended = ended_at if ended_at else now.strftime(fmt)

    # ── Build event ─────────────────────────────────────────────
    event = {
        "device_event_id": str(_uuid.uuid4()),
        "manifest_item_id": manifest_item_id,
        "started_at": event_started,
        "ended_at": event_ended,
        "duration_ms": duration_ms,
        "result": result,
    }
    if reason:
        event["reason"] = reason

    # ── Write (append-only) ──────────────────────────────────────
    pop_dir = root / "pop"
    pop_dir.mkdir(parents=True, exist_ok=True)

    log_path = pop_dir / "events.log"
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

    return event["device_event_id"]
