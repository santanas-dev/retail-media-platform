"""KSO Player PoP Local Writer — safe append-only JSONL writer.

Writes PlaybackEventDraft to {root}/pop/pending/player_events.jsonl.
Append-only, one JSON line per event, flush + fsync after each write.

NO backend, NO HTTP, NO auth, NO secret, NO media bytes.
Player writes locally; sidecar reads later (separate process).

Fail silent: invalid records are skipped, write errors return error status.
"""

import json as _json
import os as _os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from kso_player.events import (
    PlaybackEventDraft,
    EVENT_TYPE_WOULD_PLAY,
    EVENT_TYPE_BLOCKED,
    EVENT_TYPE_NOT_READY,
    EVENT_TYPE_ERROR,
    EVENT_STATUS_DRAFT,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

POP_PENDING_DIR = "pop/pending"
POP_JSONL_FILE = "player_events.jsonl"
SCHEMA_VERSION = 1

# ── Write result status ────────────────────────────────────────────

STATUS_WRITTEN = "written"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"

# ── Write result reasons ───────────────────────────────────────────

REASON_WRITTEN = "written"
REASON_INVALID_EVENT = "invalid_event"
REASON_UNSAFE_RECORD = "unsafe_record"
REASON_WRITE_FAILED = "write_failed"

# ── Allowed safety states ──────────────────────────────────────────

ALLOWED_SAFETY_STATES = frozenset({
    "unknown", "idle", "transaction", "payment", "receipt",
    "service", "error", "maintenance", "offline",
})

# ── Allowed event types ────────────────────────────────────────────

ALLOWED_EVENT_TYPES = frozenset({
    EVENT_TYPE_WOULD_PLAY, EVENT_TYPE_BLOCKED,
    EVENT_TYPE_NOT_READY, EVENT_TYPE_ERROR,
})

# ── Allowed session actions ────────────────────────────────────────

ALLOWED_SESSION_ACTIONS = frozenset({"play", "hold", "stop"})

# ── Allowed session reasons ────────────────────────────────────────

ALLOWED_SESSION_REASONS = frozenset({
    "ready", "safety_blocked", "playlist_not_ready",
    "no_items", "invalid_state",
})

# ── Allowed result values ──────────────────────────────────────────

ALLOWED_RESULTS = frozenset({
    "would_play", "blocked", "not_ready", "error",
})

# ── Forbidden substrings (checked in record values) ─────────────────

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
    "filename", "manifest_item_id", "sha256",
    "stacktrace",
})

# ── Forbidden top-level keys in JSONL record ───────────────────────

FORBIDDEN_KEYS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives",
    "backend_base_url", "device_code",
    "filename", "manifest_item_id", "sha256",
    "full_manifest", "media_bytes", "stacktrace",
    "absolute_path",
})

# ── Allowed keys in JSONL record ───────────────────────────────────

ALLOWED_RECORD_KEYS = frozenset({
    "schema_version",
    "event_type",
    "event_status",
    "created_at",
    "started_at",
    "ended_at",
    "duration_ms",
    "playback_allowed",
    "session_action",
    "session_reason",
    "selected_order",
    "selected_content_type",
    "safety_state",
    "result",
})

# ── Max line size ──────────────────────────────────────────────────

MAX_LINE_SIZE_BYTES = 4096


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopWriteResult:
    """Safe result of a PoP write operation.

    Never contains paths, secrets, tokens, media bytes, or backend URLs.
    """

    status: str = STATUS_ERROR       # written | skipped | error
    written: bool = False
    reason: str = REASON_WRITE_FAILED
    event_type: Optional[str] = None
    event_status: Optional[str] = None
    line_size_bytes: int = 0


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_forbidden(value: str) -> bool:
    """Returns True if value contains any forbidden substring."""
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════
# Record builder
# ══════════════════════════════════════════════════════════════════════

def build_pop_jsonl_record(
    event_draft: PlaybackEventDraft,
    safety_state: Optional[str] = None,
    now: Optional[str] = None,
) -> Optional[dict]:
    """Build a safe JSONL record dict from a PlaybackEventDraft.

    Returns None if the event draft or safety_state is invalid/unsafe.
    Returns a dict with ONLY allowed keys otherwise.

    Args:
        event_draft: PlaybackEventDraft from build_playback_event_draft().
        safety_state: KSO screen state (must be in ALLOWED_SAFETY_STATES).
        now: Optional ISO8601 timestamp (defaults to current UTC).

    Returns:
        dict with allowed keys, or None if invalid/unsafe.
    """
    if now is None:
        now = _now_iso()

    # ── Validate event_draft ────────────────────────────────────
    if not isinstance(event_draft, PlaybackEventDraft):
        return None

    et = getattr(event_draft, "event_type", None)
    if et not in ALLOWED_EVENT_TYPES:
        return None

    es = getattr(event_draft, "event_status", EVENT_STATUS_DRAFT)
    if es != EVENT_STATUS_DRAFT:
        return None

    # ── Validate safety_state ───────────────────────────────────
    if safety_state is None:
        return None

    if not isinstance(safety_state, str):
        return None

    ss = safety_state.strip().lower()
    if ss not in ALLOWED_SAFETY_STATES:
        return None

    # ── Validate individual fields ──────────────────────────────

    sa = getattr(event_draft, "session_action", "")
    if sa not in ALLOWED_SESSION_ACTIONS:
        return None

    sr = getattr(event_draft, "session_reason", "")
    if sr not in ALLOWED_SESSION_REASONS:
        return None

    # ── Derive result from event_type ───────────────────────────
    result = et  # event_type doubles as result

    pa = getattr(event_draft, "playback_allowed", False)
    so = getattr(event_draft, "selected_order", None)
    sct = getattr(event_draft, "selected_content_type", None)
    sdm = getattr(event_draft, "selected_duration_ms", None)
    started = getattr(event_draft, "started_at", None)
    ended = getattr(event_draft, "would_end_at", None)
    created = getattr(event_draft, "created_at", now)

    # ── Build record with only allowed keys ────────────────────
    record = {
        "schema_version": SCHEMA_VERSION,
        "event_type": et,
        "event_status": es,
        "created_at": created,
        "started_at": started if started else None,
        "ended_at": ended if ended else None,
        "duration_ms": sdm if isinstance(sdm, int) and sdm >= 0 else 0,
        "playback_allowed": bool(pa),
        "session_action": sa,
        "session_reason": sr,
        "selected_order": so if isinstance(so, int) else None,
        "selected_content_type": sct if isinstance(sct, str) else None,
        "safety_state": ss,
        "result": result,
    }

    # ── Safety scan: check all string values ───────────────────
    for key, val in record.items():
        if _check_forbidden(val):
            return None

    # ── Ensure no forbidden keys leaked ────────────────────────
    for key in record:
        if key in FORBIDDEN_KEYS or key not in ALLOWED_RECORD_KEYS:
            return None

    return record


# ══════════════════════════════════════════════════════════════════════
# Write function
# ══════════════════════════════════════════════════════════════════════

def write_pop_event(
    root,
    event_draft: PlaybackEventDraft,
    safety_state: Optional[str] = None,
    now: Optional[str] = None,
) -> PopWriteResult:
    """Write a safe playback event to pop/pending/player_events.jsonl.

    Steps:
        1. Build safe JSONL record via build_pop_jsonl_record()
        2. Validate record (forbidden checks)
        3. Create pop/pending/ dir if missing
        4. Append one JSON line + newline
        5. flush + fsync
        6. Return safe PopWriteResult

    Fail silent: never raises. Invalid/skipped → PopWriteResult with status.
    Write errors → PopWriteResult with status=error.

    Args:
        root: Agent root path (str or Path).
        event_draft: PlaybackEventDraft to write.
        safety_state: KSO screen state.
        now: Optional ISO8601 timestamp.

    Returns:
        PopWriteResult — always safe, never raises.
    """
    root = Path(root)

    # ── Build record ────────────────────────────────────────────
    try:
        record = build_pop_jsonl_record(event_draft, safety_state, now)
    except Exception:
        return PopWriteResult(
            status=STATUS_SKIPPED,
            written=False,
            reason=REASON_INVALID_EVENT,
        )

    if record is None:
        # Determine reason
        if not isinstance(event_draft, PlaybackEventDraft):
            return PopWriteResult(
                status=STATUS_ERROR,
                written=False,
                reason=REASON_INVALID_EVENT,
            )
        if safety_state is None or safety_state not in ALLOWED_SAFETY_STATES:
            return PopWriteResult(
                status=STATUS_SKIPPED,
                written=False,
                reason=REASON_UNSAFE_RECORD,
                event_type=getattr(event_draft, "event_type", None),
                event_status=EVENT_STATUS_DRAFT,
            )
        return PopWriteResult(
            status=STATUS_ERROR,
            written=False,
            reason=REASON_INVALID_EVENT,
            event_type=getattr(event_draft, "event_type", None),
            event_status=EVENT_STATUS_DRAFT,
        )

    # ── Validate record post-build ──────────────────────────────
    try:
        record_json = _json.dumps(record, ensure_ascii=False, sort_keys=True)
    except Exception:
        return PopWriteResult(
            status=STATUS_SKIPPED,
            written=False,
            reason=REASON_UNSAFE_RECORD,
            event_type=record.get("event_type"),
            event_status=record.get("event_status"),
        )

    line = record_json + "\n"
    line_bytes = len(line.encode("utf-8"))

    # ── Size limit check ────────────────────────────────────────
    if line_bytes > MAX_LINE_SIZE_BYTES:
        return PopWriteResult(
            status=STATUS_SKIPPED,
            written=False,
            reason=REASON_UNSAFE_RECORD,
            event_type=record.get("event_type"),
            event_status=record.get("event_status"),
        )

    # ── Write ───────────────────────────────────────────────────
    try:
        pending_dir = root / POP_PENDING_DIR
        pending_dir.mkdir(parents=True, exist_ok=True)

        filepath = pending_dir / POP_JSONL_FILE

        with open(filepath, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            _os.fsync(fh.fileno())

    except Exception:
        return PopWriteResult(
            status=STATUS_ERROR,
            written=False,
            reason=REASON_WRITE_FAILED,
            event_type=record.get("event_type"),
            event_status=record.get("event_status"),
        )

    return PopWriteResult(
        status=STATUS_WRITTEN,
        written=True,
        reason=REASON_WRITTEN,
        event_type=record.get("event_type"),
        event_status=record.get("event_status"),
        line_size_bytes=line_bytes,
    )
