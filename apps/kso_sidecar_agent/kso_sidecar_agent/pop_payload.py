"""KSO Sidecar PoP Backend Payload Builder — safe in-memory payload assembly.

Reads pop/pending/player_events.jsonl, classifies eligible events,
maps selected_order to manifest_item_id (and related IDs) from current manifest,
and builds an in-memory PopPayloadEnvelope for future backend send.

NO backend send, NO HTTP, NO file move, NO delete.
Only returns safe aggregates — never raw payload, paths, or secrets.
Payload envelope and event dataclasses use repr=False for sensitive fields.
"""

import json as _json
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from kso_sidecar_agent.pop_pickup import (
    POP_PENDING_DIR,
    POP_JSONL_FILE,
    ALLOWED_RECORD_KEYS,
    CLASS_ELIGIBLE,
    CLASS_DRAFT,
    CLASS_DIAGNOSTIC,
    CLASS_QUARANTINE,
    CLASS_INVALID,
    SCAN_OK,
    SCAN_WARNING,
    SCAN_ERROR,
    _validate_record,
    classify_pop_event,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

DEFAULT_MAX_EVENTS = 100

FORBIDDEN_IN_OUTPUT = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "customer_id", "phone", "email",
    "receipt_number", "fiscal_data",
    "local_path", "file_path",
    "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
    "backend_base_url", "127.0.0.1", "device_code",
    "filename", "sha256",
    "full_manifest", "media_bytes", "stacktrace",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclasses (repr=False for sensitive/internal fields)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopPayloadEvent:
    """A single backend payload event.

    Internal-only: contains manifest_item_id and other FK UUIDs.
    repr=False prevents accidental logging of sensitive fields.

    selected_order and selected_content_type are SAFE fields —
    they carry the slot position and content type from the player event,
    used by the backend for server-side KSO manifest correlation.
    """

    device_event_id: str = field(default="", repr=False)
    manifest_item_id: Optional[str] = field(default=None, repr=False)
    manifest_version_id: Optional[str] = field(default=None, repr=False)
    campaign_id: Optional[str] = field(default=None, repr=False)
    publication_target_id: Optional[str] = field(default=None, repr=False)
    schedule_item_id: Optional[str] = field(default=None, repr=False)
    played_at: Optional[str] = None
    duration_ms: int = 0
    play_status: str = "completed"
    selected_order: Optional[int] = None
    selected_content_type: Optional[str] = None
    # — Screensaver extension: safe creative_code from backend manifest —
    creative_code: Optional[str] = field(default=None, repr=False)


@dataclass
class PopPayloadEnvelope:
    """Batch envelope for backend submission.

    Internal-only: repr=False — payload body must never appear in logs.
    """

    batch_id: str = field(default="", repr=False)
    sent_at: Optional[str] = None
    events: list = field(default_factory=list, repr=False)


@dataclass
class PopPayloadBuildResult:
    """Safe aggregated result of payload building.

    Never contains raw JSON, event records, manifest_item_id,
    filename, sha256, paths, or secrets.
    """

    status: str = SCAN_OK
    payload_events: int = 0
    skipped_events: int = 0
    invalid_events: int = 0
    quarantine_events: int = 0
    diagnostic_events: int = 0
    draft_events: int = 0
    batch_limited: bool = False
    max_events: int = DEFAULT_MAX_EVENTS
    # Internal-only — not exposed in safe output
    _envelope: Optional[PopPayloadEnvelope] = field(default=None, repr=False)


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_uuid() -> str:
    return str(_uuid.uuid4())


def _find_manifest_item(manifest_items: Optional[list], selected_order: int) -> Optional[dict]:
    """Find a manifest item dict by order. Returns None if not found."""
    if not manifest_items or not isinstance(manifest_items, list):
        return None
    for item in manifest_items:
        if not isinstance(item, dict):
            continue
        try:
            if item.get("order") == selected_order:
                return item
        except Exception:
            continue
    return None


def _check_forbidden_in_output(value: str) -> bool:
    """Return True if value contains any forbidden substring for safe output."""
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for fb in FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════
# Payload builder
# ══════════════════════════════════════════════════════════════════════

def build_pop_backend_payload(
    root,
    max_events: int = DEFAULT_MAX_EVENTS,
    now: Optional[str] = None,
) -> PopPayloadBuildResult:
    """Build in-memory backend payload from eligible player events.

    Pipeline:
        1. Read pop/pending/player_events.jsonl
        2. Classify each event (via pop_pickup)
        3. Only CLASS_ELIGIBLE events → manifest mapping → PopPayloadEvent
        4. Assemble PopPayloadEnvelope (batch_id + events)
        5. Return PopPayloadBuildResult (safe aggregates only)

    NO backend send, NO HTTP, NO file move, NO delete.

    Args:
        root: Agent root path (str or Path).
        max_events: Max payload events (default 100).
        now: Optional ISO8601 timestamp for sent_at.

    Returns:
        PopPayloadBuildResult — always safe, never raises.
        Payload envelope accessible via result._envelope (internal only).
    """
    root = Path(root)
    jsonl_path = root / POP_PENDING_DIR / POP_JSONL_FILE
    if now is None:
        now = _now_iso()

    result = PopPayloadBuildResult(max_events=max_events)
    envelope = PopPayloadEnvelope(
        batch_id=_gen_uuid(),
        sent_at=now,
        events=[],
    )
    result._envelope = envelope

    if max_events <= 0:
        result.status = SCAN_ERROR
        return result

    # ── File missing → empty ok ──────────────────────────────────
    if not jsonl_path.exists() or not jsonl_path.is_file():
        result.status = SCAN_OK
        return result

    # ── Read manifest for mapping ───────────────────────────────
    manifest_data: Optional[dict] = None
    manifest_items: Optional[list] = None
    try:
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

    # ── Check media cache ───────────────────────────────────────
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

    # Legacy media check incomplete — try KSO-aware check
    if media_cache_complete is not True and manifest_items is not None:
        from kso_sidecar_agent.pop_pickup import _kso_media_cache_check
        kso_check = _kso_media_cache_check(root, manifest_items)
        if kso_check is True:
            media_cache_complete = True

    # ── Read and process ────────────────────────────────────────
    try:
        raw = jsonl_path.read_text(encoding="utf-8")
    except Exception:
        result.status = SCAN_ERROR
        return result

    lines = raw.split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Parse
        try:
            record = _json.loads(stripped)
        except Exception:
            result.invalid_events += 1
            continue

        if not isinstance(record, dict):
            result.invalid_events += 1
            continue

        # Validate
        if _validate_record(record) is not None:
            result.invalid_events += 1
            continue

        # Classify
        classification = classify_pop_event(
            record,
            manifest_items=manifest_items,
            media_cache_complete=media_cache_complete,
        )

        if classification.classification == CLASS_ELIGIBLE:
            # Check max_events
            if len(envelope.events) >= max_events:
                result.batch_limited = True
                break

            # Manifest mapping
            selected_order = record.get("selected_order")
            manifest_item = _find_manifest_item(manifest_items, selected_order) if isinstance(selected_order, int) else None

            if manifest_item is None:
                # Mapping lost — should not happen (already checked in classify)
                result.quarantine_events += 1
                continue

            payload_event = PopPayloadEvent(
                device_event_id=_gen_uuid(),
                manifest_item_id=manifest_item.get("manifest_item_id"),
                manifest_version_id=manifest_data.get("manifest_version_id") if manifest_data else None,
                campaign_id=manifest_item.get("campaign_id"),
                publication_target_id=manifest_data.get("publication_target_id") if manifest_data else None,
                schedule_item_id=manifest_item.get("schedule_item_id"),
                played_at=record.get("started_at"),
                duration_ms=record.get("duration_ms", 0),
                play_status="completed",
                selected_order=record.get("selected_order"),
                selected_content_type=record.get("selected_content_type"),
                creative_code=record.get("creative_code"),
            )

            envelope.events.append(payload_event)

        elif classification.classification == CLASS_DRAFT:
            result.draft_events += 1
        elif classification.classification == CLASS_DIAGNOSTIC:
            result.diagnostic_events += 1
        elif classification.classification == CLASS_QUARANTINE:
            result.quarantine_events += 1
        else:
            result.invalid_events += 1

    result.payload_events = len(envelope.events)
    result.skipped_events = result.draft_events + result.diagnostic_events + result.quarantine_events

    # ── Determine status ────────────────────────────────────────
    if result.invalid_events > 0 and result.payload_events == 0:
        result.status = SCAN_ERROR
    elif result.invalid_events > 0 or result.quarantine_events > 0:
        result.status = SCAN_WARNING
    else:
        result.status = SCAN_OK

    return result


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_payload_build_result(result: PopPayloadBuildResult) -> str:
    """Return a safe aggregated string of the payload build result.

    Never prints payload body, manifest_item_id, batch_id,
    campaign_id, filename, sha256, paths, or secrets.
    """
    lines = [
        f"payload_status:      {result.status}",
        f"payload_events:      {result.payload_events}",
        f"skipped_events:      {result.skipped_events}",
        f"invalid_events:      {result.invalid_events}",
        f"quarantine_events:   {result.quarantine_events}",
        f"diagnostic_events:   {result.diagnostic_events}",
        f"draft_events:        {result.draft_events}",
        f"batch_limited:       {str(result.batch_limited).lower()}",
        f"max_events:          {result.max_events}",
    ]
    return "\n".join(lines)
