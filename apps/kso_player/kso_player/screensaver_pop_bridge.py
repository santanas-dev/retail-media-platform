"""Screensaver PoP Bridge — ScreensaverPoPDraft → sidecar JSONL record adapter.

Converts ScreensaverPoPDraft (from X11 runner) into a record
compatible with sidecar's pop/pending/player_events.jsonl format.

Design: docs/audit/x11-runner-pop-bridge-design.md
Prerequisites: 38.2.2 — sidecar media cache bridge, 38.2.1 — creative_code
"""

import hashlib as _hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from kso_player.screensaver_creative import (
    ScreensaverPoPDraft,
    SCREENSAVER_EVENT_VISIBLE,
    SCREENSAVER_EVENT_HIDDEN,
    SCREENSAVER_EVENT_PLAYBACK_STARTED,
    SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
    SCREENSAVER_EVENT_BLOCKED,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

MODULE_NAME = "screensaver_pop_bridge"
MODULE_VERSION = "0.1.0"
SCHEMA_VERSION = 1

# — Event type mapping: screensaver → sidecar-compatible —
_EVENT_TYPE_MAP = {
    SCREENSAVER_EVENT_VISIBLE: "impression",
    SCREENSAVER_EVENT_HIDDEN: "completed",
    SCREENSAVER_EVENT_PLAYBACK_STARTED: "playback_started",
    SCREENSAVER_EVENT_PLAYBACK_COMPLETED: "playback_completed",
    SCREENSAVER_EVENT_BLOCKED: "blocked",
}

# — Event status mapping —
_STATUS_DRAFT = "draft"
_STATUS_COMPLETED = "completed"

# Events that produce a completed record (eligible for backend send):
_COMPLETED_EVENT_TYPES = frozenset({
    SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
})

# Events that are draft (not eligible, but tracked):
_DRAFT_EVENT_TYPES = frozenset({
    SCREENSAVER_EVENT_VISIBLE,
    SCREENSAVER_EVENT_HIDDEN,
    SCREENSAVER_EVENT_PLAYBACK_STARTED,
    SCREENSAVER_EVENT_BLOCKED,
})

# — Allowed safety states —
ALLOWED_SAFETY_STATES = frozenset({
    "unknown", "idle", "transaction", "payment", "receipt",
    "service", "error", "maintenance", "offline",
})

# — Allowed session actions/reasons —
_ALLOWED_SESSION_ACTIONS = frozenset({"play", "hold", "stop"})
_ALLOWED_SESSION_REASONS = frozenset({
    "ready", "safety_blocked", "playlist_not_ready",
    "no_items", "invalid_state",
})

# — Forbidden substrings in any field —
_FORBIDDEN_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path", "absolute_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
    "backend_base_url", "127.0.0.1",
    "filename", "manifest_item_id", "sha256",
    "storage_ref", "minio", "s3://",
    "stacktrace",
})

# — Forbidden top-level keys —
_FORBIDDEN_KEYS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path", "absolute_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives",
    "backend_base_url", "device_code",
    "filename", "manifest_item_id", "sha256",
    "storage_ref", "minio", "s3",
    "full_manifest", "media_bytes", "stacktrace",
})

# — Allowed record keys (compatible with sidecar pop_pickup.py) —
# Extended with creative_code and media_available for screensaver PoP
ALLOWED_SCREENSAVER_RECORD_KEYS = frozenset({
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
    # — Screensaver extensions —
    "creative_code",
    "media_available",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ScreensaverPopRecordResult:
    """Result of building a screensaver PoP record for sidecar JSONL.

    Safe fields only. NEVER contains raw path, backend URL,
    token, secret, receipt, fiscal, customer, card, barcode.
    """

    built: bool = False
    reason: str = "invalid_event"
    event_type: str = ""
    event_status: str = _STATUS_DRAFT
    creative_code: str = ""

    # Internal — NEVER exposed in safe output
    _record: Optional[dict] = None

    def to_safe_dict(self) -> dict:
        return {
            "built": self.built,
            "reason": self.reason,
            "event_type": self.event_type,
            "event_status": self.event_status,
            "creative_code": self.creative_code,
        }


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_forbidden(value) -> bool:
    """True if value contains any forbidden substring."""
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for fb in _FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return True
    return False


def _gen_idempotency_code(creative_code: str, event_type: str, started_at: str) -> str:
    """Generate a deterministic idempotency code from safe fields.

    SHA-256 of canonical concatenation. Never includes:
    UUID, file_path, backend_url, token, secret, receipt, fiscal.
    """
    canonical = f"{creative_code}|{event_type}|{started_at}"
    return _hashlib.sha256(canonical.encode()).hexdigest()[:32]


# ══════════════════════════════════════════════════════════════════════
# Core: build screensaver PoP record
# ══════════════════════════════════════════════════════════════════════

def build_screensaver_pop_record(
    pop_draft: ScreensaverPoPDraft,
    safety_state: str = "idle",
    slot_order: int = 0,
    content_type: str = "",
    now: Optional[str] = None,
) -> ScreensaverPopRecordResult:
    """Convert a ScreensaverPoPDraft to a sidecar-compatible JSONL record.

    Maps screensaver event types to sidecar-compatible types.
    Only playback_completed events get event_status=completed (eligible
    for backend send). All other events stay draft.

    Playback events require media_available=True — otherwise blocked.

    Args:
        pop_draft: ScreensaverPoPDraft from the X11 runner.
        safety_state: KSO screen state (default "idle").
        slot_order: The creative's slot_order.
        content_type: The creative's content_type.
        now: Optional ISO8601 timestamp.

    Returns:
        ScreensaverPopRecordResult — always safe, never raises.
    """
    if now is None:
        now = _now_iso()

    # ── Validate input ────────────────────────────────────────────
    if not isinstance(pop_draft, ScreensaverPoPDraft):
        return ScreensaverPopRecordResult(reason="invalid_event")

    # ── Map event type ────────────────────────────────────────────
    screensaver_type = pop_draft.event_type
    mapped_type = _EVENT_TYPE_MAP.get(screensaver_type)
    if mapped_type is None:
        return ScreensaverPopRecordResult(
            reason="unknown_event_type",
            event_type=screensaver_type,
        )

    # ── Determine event status ────────────────────────────────────
    if screensaver_type in _COMPLETED_EVENT_TYPES:
        event_status = _STATUS_COMPLETED
    else:
        event_status = _STATUS_DRAFT

    # ── Playback gate: media_available must be True ──────────────
    if screensaver_type in (
        SCREENSAVER_EVENT_PLAYBACK_STARTED,
        SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
    ):
        if not pop_draft.media_available:
            # Record as blocked — no playback without media
            mapped_type = "blocked"
            event_status = _STATUS_DRAFT

    # ── Creative code ─────────────────────────────────────────────
    creative_code = pop_draft.creative_code or ""
    if _check_forbidden(creative_code):
        return ScreensaverPopRecordResult(
            reason="unsafe_creative_code",
            creative_code=creative_code[:32],
        )

    # ── Map session action / reason ───────────────────────────────
    if pop_draft.visible and mapped_type in ("impression", "playback_started", "playback_completed"):
        session_action = "play"
        session_reason = "ready"
    elif mapped_type == "blocked":
        session_action = "hold"
        session_reason = "safety_blocked"
    else:
        session_action = "stop"
        session_reason = "invalid_state"

    # ── Validate safety_state ─────────────────────────────────────
    ss = safety_state.strip().lower()
    if ss not in ALLOWED_SAFETY_STATES:
        ss = "idle"

    # ── Build record ──────────────────────────────────────────────
    record = {
        "schema_version": SCHEMA_VERSION,
        "event_type": mapped_type,
        "event_status": event_status,
        "created_at": now,
        "started_at": pop_draft.started_at_utc or None,
        "ended_at": pop_draft.ended_at_utc or None,
        "duration_ms": pop_draft.duration_ms or 0,
        "playback_allowed": pop_draft.media_available and pop_draft.visible,
        "session_action": session_action,
        "session_reason": session_reason,
        "selected_order": slot_order if isinstance(slot_order, int) and slot_order >= 0 else None,
        "selected_content_type": content_type if content_type else None,
        "safety_state": ss,
        "result": mapped_type,
        # — Screensaver extensions —
        "creative_code": creative_code if creative_code else None,
        "media_available": pop_draft.media_available,
    }

    # ── Safety scan: check all string values ──────────────────────
    for key, val in record.items():
        if _check_forbidden(val):
            return ScreensaverPopRecordResult(
                reason="unsafe_record",
                event_type=mapped_type,
                creative_code=creative_code[:32],
            )

    # ── Ensure no forbidden keys leaked ────────────────────────────
    for key in record:
        if key in _FORBIDDEN_KEYS:
            return ScreensaverPopRecordResult(
                reason=f"forbidden_key_{key}",
                event_type=mapped_type,
            )

    # ── Validate only allowed keys present ────────────────────────
    for key in record:
        if key not in ALLOWED_SCREENSAVER_RECORD_KEYS:
            return ScreensaverPopRecordResult(
                reason=f"unknown_key_{key}",
                event_type=mapped_type,
            )

    return ScreensaverPopRecordResult(
        built=True,
        reason="built",
        event_type=mapped_type,
        event_status=event_status,
        creative_code=creative_code,
        _record=record,
    )


# ══════════════════════════════════════════════════════════════════════
# Idempotency code builder
# ══════════════════════════════════════════════════════════════════════

def build_screensaver_event_code(
    creative_code: str,
    event_type: str,
    started_at_utc: str = "",
    slot_order: int = 0,
) -> str:
    """Build a deterministic idempotency code for a screensaver PoP event.

    Format: scr-<hash[:16]>
    Hash = SHA-256(creative_code|event_type|started_at|slot_order)

    Args:
        creative_code: Backend creative_code.
        event_type: Screensaver event type.
        started_at_utc: ISO8601 start time.
        slot_order: Slot position.

    Returns:
        Safe 20-char idempotency code (scr- prefix + 16 hex chars).
    """
    canonical = f"{creative_code}|{event_type}|{started_at_utc}|{slot_order}"
    digest = _hashlib.sha256(canonical.encode()).hexdigest()
    return f"scr-{digest[:16]}"
