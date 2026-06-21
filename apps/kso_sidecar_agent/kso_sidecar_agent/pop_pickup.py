"""KSO Sidecar PoP Pickup — safe parser/classifier for local player events.

Reads pop/pending/player_events.jsonl, validates each line, classifies
events as draft/eligible/diagnostic/quarantine/invalid.

Read-only: never deletes, never moves, never sends to backend.
Only returns safe aggregated ScanResult — no raw events, paths, or secrets.
"""

import json as _json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ══════════════════════════════════════════════════════════════════════
# Constants — mirrored from pop_writer.py for independence
# ══════════════════════════════════════════════════════════════════════

POP_PENDING_DIR = "pop/pending"
POP_JSONL_FILE = "player_events.jsonl"

# ── Allowed keys in JSONL record ────────────────────────────────────

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

# ── Allowed event types ─────────────────────────────────────────────

ALLOWED_EVENT_TYPES = frozenset({
    "would_play", "blocked", "not_ready", "error",
})

# ── Allowed event statuses ──────────────────────────────────────────

ALLOWED_EVENT_STATUSES = frozenset({
    "draft", "completed", "blocked", "failed",
})

# ── Allowed safety states ───────────────────────────────────────────

ALLOWED_SAFETY_STATES = frozenset({
    "unknown", "idle", "transaction", "payment", "receipt",
    "service", "error", "maintenance", "offline",
})

# ── Allowed session actions / reasons ───────────────────────────────

ALLOWED_SESSION_ACTIONS = frozenset({"play", "hold", "stop"})
ALLOWED_SESSION_REASONS = frozenset({
    "ready", "safety_blocked", "playlist_not_ready",
    "no_items", "invalid_state",
})

# ── Forbidden substrings ────────────────────────────────────────────

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

# ── Forbidden top-level keys ────────────────────────────────────────

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

# ── Classification ──────────────────────────────────────────────────

CLASS_DRAFT = "draft"
CLASS_ELIGIBLE = "eligible"
CLASS_DIAGNOSTIC = "diagnostic"
CLASS_QUARANTINE = "quarantine"
CLASS_INVALID = "invalid"

# ── Classification reasons ──────────────────────────────────────────

REASON_DRAFT_NOT_POP = "draft_not_pop"
REASON_BLOCKED_NOT_POP = "blocked_not_pop"
REASON_FAILED_NOT_POP = "failed_not_pop"
REASON_ELIGIBLE = "eligible"
REASON_MANIFEST_MAPPING_MISSING = "manifest_mapping_missing"
REASON_MANIFEST_UNAVAILABLE = "manifest_unavailable"
REASON_MEDIA_CACHE_INCOMPLETE = "media_cache_incomplete"
REASON_INVALID_JSON = "invalid_json"
REASON_INVALID_SCHEMA = "invalid_schema"
REASON_FORBIDDEN_FIELD = "forbidden_field"
REASON_FORBIDDEN_VALUE = "forbidden_value"
REASON_UNKNOWN_STATUS = "unknown_status"

# ── Scan status ─────────────────────────────────────────────────────

SCAN_OK = "ok"
SCAN_WARNING = "warning"
SCAN_ERROR = "error"


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopPickupClassification:
    """Safe classification of a single PoP event line.

    Never contains raw event data, paths, secrets, or backend URLs.
    """

    line_number: int = 0
    classification: str = CLASS_INVALID       # draft | eligible | diagnostic | quarantine | invalid
    reason: str = REASON_INVALID_JSON
    backend_eligible: bool = False
    event_type: Optional[str] = None
    event_status: Optional[str] = None
    safety_state: Optional[str] = None
    selected_order: Optional[int] = None


@dataclass
class PopPickupScanResult:
    """Safe aggregated scan result.

    Never contains raw JSON lines, full event records, paths,
    manifest_item_id, filename, sha256, or secrets.
    """

    status: str = SCAN_OK                     # ok | warning | error
    total_lines: int = 0
    valid_events: int = 0
    invalid_lines: int = 0
    draft_events: int = 0
    eligible_events: int = 0
    diagnostic_events: int = 0
    quarantine_events: int = 0
    backend_eligible_events: int = 0


# ══════════════════════════════════════════════════════════════════════
# Validation helpers
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden(value) -> bool:
    """Return True if value contains any forbidden substring."""
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return True
    return False


def _validate_record(record: dict) -> Optional[str]:
    """Validate a JSONL record dict.

    Returns None if valid, or a reason string if invalid.
    """
    if not isinstance(record, dict):
        return REASON_INVALID_JSON

    # ── Check for forbidden top-level keys ──────────────────────
    for key in record:
        if key in FORBIDDEN_KEYS:
            return REASON_FORBIDDEN_FIELD
        if key not in ALLOWED_RECORD_KEYS:
            return REASON_INVALID_SCHEMA

    # ── Validate required fields ────────────────────────────────
    if record.get("event_type") not in ALLOWED_EVENT_TYPES:
        return REASON_INVALID_SCHEMA

    es = record.get("event_status", "")
    if es not in ALLOWED_EVENT_STATUSES:
        return REASON_UNKNOWN_STATUS

    ss = record.get("safety_state", "")
    if ss not in ALLOWED_SAFETY_STATES:
        return REASON_INVALID_SCHEMA

    # ── Check all string values for forbidden substrings ────────
    for key, val in record.items():
        if _check_forbidden(val):
            return REASON_FORBIDDEN_VALUE
        if _check_forbidden(key):
            return REASON_FORBIDDEN_FIELD

    return None


# ══════════════════════════════════════════════════════════════════════
# Manifest mapping
# ══════════════════════════════════════════════════════════════════════

def _find_manifest_item_by_order(
    manifest_items: Optional[list],
    selected_order: int,
) -> bool:
    """Check if a manifest item exists with the given order value.

    Returns True if found, False otherwise.
    Does NOT return manifest_item_id, filename, or sha256.
    """
    if not manifest_items or not isinstance(manifest_items, list):
        return False

    for item in manifest_items:
        if not isinstance(item, dict):
            continue
        try:
            item_order = item.get("order")
            if isinstance(item_order, int) and item_order == selected_order:
                return True
        except Exception:
            continue

    return False


# ══════════════════════════════════════════════════════════════════════
# Classification
# ══════════════════════════════════════════════════════════════════════

def classify_pop_event(
    record: dict,
    manifest_items: Optional[list] = None,
    media_cache_complete: Optional[bool] = None,
) -> PopPickupClassification:
    """Classify a single parsed PoP event record.

    Pure logic — no file I/O, no HTTP, no auth.

    Args:
        record: Parsed JSON dict from JSONL line (already validated).
        manifest_items: Optional list of manifest item dicts for order mapping.
        media_cache_complete: Optional bool — is the local media cache complete?

    Returns:
        PopPickupClassification — always safe, never raises.
    """
    # ── Basic safety ────────────────────────────────────────────
    if not isinstance(record, dict):
        return PopPickupClassification(classification=CLASS_INVALID,
                                       reason=REASON_INVALID_JSON)

    # Extract injected metadata before validation
    line_num = record.pop("_line_number", 0)
    event_status = record.get("event_status", "")
    event_type = record.get("event_type", "")
    safety_state = record.get("safety_state", "")
    selected_order = record.get("selected_order")

    base = PopPickupClassification(
        line_number=line_num,
        event_type=event_type,
        event_status=event_status,
        safety_state=safety_state,
        selected_order=selected_order if isinstance(selected_order, int) else None,
    )

    # ── Validate schema first ──────────────────────────────────
    validation_error = _validate_record(record)
    if validation_error is not None:
        base.classification = CLASS_INVALID
        base.reason = validation_error
        base.backend_eligible = False
        return base

    # ── Classify by event_status ────────────────────────────────
    if event_status == "draft":
        base.classification = CLASS_DRAFT
        base.reason = REASON_DRAFT_NOT_POP
        base.backend_eligible = False
        return base

    if event_status == "blocked":
        base.classification = CLASS_DIAGNOSTIC
        base.reason = REASON_BLOCKED_NOT_POP
        base.backend_eligible = False
        return base

    if event_status == "failed":
        base.classification = CLASS_DIAGNOSTIC
        base.reason = REASON_FAILED_NOT_POP
        base.backend_eligible = False
        return base

    # ── event_status == "completed" → check eligibility ────────
    if event_status == "completed":
        # Must be idle
        if safety_state != "idle":
            base.classification = CLASS_QUARANTINE
            base.reason = REASON_BLOCKED_NOT_POP
            base.backend_eligible = False
            return base

        # Must have selected_order
        if not isinstance(selected_order, int):
            base.classification = CLASS_QUARANTINE
            base.reason = REASON_MANIFEST_MAPPING_MISSING
            base.backend_eligible = False
            return base

        # Must map to manifest item
        if manifest_items is None:
            base.classification = CLASS_QUARANTINE
            base.reason = REASON_MANIFEST_UNAVAILABLE
            base.backend_eligible = False
            return base

        if not _find_manifest_item_by_order(manifest_items, selected_order):
            base.classification = CLASS_QUARANTINE
            base.reason = REASON_MANIFEST_MAPPING_MISSING
            base.backend_eligible = False
            return base

        # Must have complete media cache
        if media_cache_complete is not True:
            base.classification = CLASS_QUARANTINE
            base.reason = REASON_MEDIA_CACHE_INCOMPLETE
            base.backend_eligible = False
            return base

        # All conditions met → eligible
        base.classification = CLASS_ELIGIBLE
        base.reason = REASON_ELIGIBLE
        base.backend_eligible = True
        return base

    # ── Unknown event_status ────────────────────────────────────
    base.classification = CLASS_QUARANTINE
    base.reason = REASON_UNKNOWN_STATUS
    base.backend_eligible = False
    return base


# ══════════════════════════════════════════════════════════════════════
# KSO-aware media cache check
# ══════════════════════════════════════════════════════════════════════


def _kso_media_cache_check(root: Path, manifest_items: list) -> Optional[bool]:
    """Check if media files exist for KSO safe manifest items.

    KSO safe items have order, content_type, duration_ms but NOT
    filename or sha256. Legacy media_cache_status() requires those.
    This function does simple existence-only check.

    Returns True if ALL items have media files present.
    Returns False if any item's media file is missing.
    Returns None if items list is empty.
    """
    if not manifest_items:
        return None

    MEDIA_CURRENT = "media/current"
    current_dir = root / MEDIA_CURRENT

    for item in manifest_items:
        if not isinstance(item, dict):
            return False

        # Try _media_ref first (KSO safe), then filename (legacy)
        media_ref = item.get("_media_ref", "")
        if media_ref:
            # KSO safe: media_ref is "media/current/slot-NNN"
            target = root / media_ref
        else:
            filename = item.get("filename", "")
            if not filename:
                return False
            target = current_dir / filename

        if not target.exists() or not target.is_file():
            return False

    return True


# ══════════════════════════════════════════════════════════════════════
# Scanner
# ══════════════════════════════════════════════════════════════════════

def scan_pending_pop_events(root) -> PopPickupScanResult:
    """Scan pop/pending/player_events.jsonl and classify all events.

    Read-only: never deletes, moves, or sends events.
    Returns only safe aggregated ScanResult — no raw events, paths, or secrets.

    Internally loads current manifest and checks media cache status
    for completed event eligibility. Falls back gracefully if
    manifest or media cache is unavailable.

    Args:
        root: Agent root path (str or Path).

    Returns:
        PopPickupScanResult — always safe, never raises.
    """
    root = Path(root)
    jsonl_path = root / POP_PENDING_DIR / POP_JSONL_FILE

    result = PopPickupScanResult()

    # ── File missing → empty ok result ──────────────────────────
    if not jsonl_path.exists() or not jsonl_path.is_file():
        result.status = SCAN_OK
        return result

    # ── Read manifest for mapping ───────────────────────────────
    manifest_items: Optional[list] = None
    try:
        # Import locally — avoids hard dependency for testing
        from kso_sidecar_agent.manifest_store import read_current_manifest
        manifest_data = read_current_manifest(root)
        manifest_items = manifest_data.get("items", [])
    except Exception:
        # Legacy format failed — try KSO safe format
        try:
            from kso_sidecar_agent.kso_safe_manifest_context import (
                read_kso_safe_manifest_context,
                get_manifest_items_for_classifier,
            )
            ctx = read_kso_safe_manifest_context(root)
            if ctx.format == "kso_safe":
                manifest_items = get_manifest_items_for_classifier(ctx)
        except Exception:
            manifest_items = None

    # ── Check media cache completeness ──────────────────────────
    media_cache_complete: Optional[bool] = None
    try:
        from kso_sidecar_agent.media_cache import media_cache_status
        mc_status = media_cache_status(root, manifest_items=manifest_items)
        items_total = mc_status.get("items_total", 0)
        items_cached = mc_status.get("items_cached", 0)
        if items_total > 0 and items_cached == items_total:
            media_cache_complete = True
        elif items_total > 0:
            media_cache_complete = False
        else:
            media_cache_complete = None
    except Exception:
        media_cache_complete = None

    # Legacy media check failed or returned incomplete — try KSO-aware check
    if media_cache_complete is not True and manifest_items is not None:
        kso_check = _kso_media_cache_check(root, manifest_items)
        if kso_check is True:
            media_cache_complete = True

    # ── Read and classify lines ─────────────────────────────────
    try:
        raw = jsonl_path.read_text(encoding="utf-8")
    except Exception:
        result.status = SCAN_ERROR
        return result

    lines = raw.split("\n")
    line_number = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        line_number += 1
        result.total_lines += 1

        # Parse JSON
        try:
            record = _json.loads(stripped)
        except Exception:
            result.invalid_lines += 1
            continue

        if not isinstance(record, dict):
            result.invalid_lines += 1
            continue

        # Validate BEFORE injecting _line_number
        validation_error = _validate_record(record)
        if validation_error is not None:
            result.invalid_lines += 1
            continue

        # Inject line number for classification
        record["_line_number"] = line_number

        result.valid_events += 1

        # Classify
        classification = classify_pop_event(
            record,
            manifest_items=manifest_items,
            media_cache_complete=media_cache_complete,
        )

        if classification.classification == CLASS_DRAFT:
            result.draft_events += 1
        elif classification.classification == CLASS_ELIGIBLE:
            result.eligible_events += 1
        elif classification.classification == CLASS_DIAGNOSTIC:
            result.diagnostic_events += 1
        elif classification.classification == CLASS_QUARANTINE:
            result.quarantine_events += 1
        else:
            result.invalid_lines += 1  # CLASS_INVALID

    result.backend_eligible_events = result.eligible_events

    # ── Determine scan status ───────────────────────────────────
    if result.invalid_lines > 0 and result.valid_events == 0:
        result.status = SCAN_ERROR
    elif result.invalid_lines > 0:
        result.status = SCAN_WARNING
    elif result.total_lines == 0:
        result.status = SCAN_OK
    else:
        result.status = SCAN_OK

    return result
