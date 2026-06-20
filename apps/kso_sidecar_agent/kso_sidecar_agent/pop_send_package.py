"""KSO Sidecar PoP Send Package Scope Core — in-memory send package builder.

Builds from ONE pending snapshot in a single locked pass:
  - backend payload (PopPayloadEnvelope)
  - PopRotationSentScope (same pending line numbers)
  - safe aggregate result

NO backend send, NO HTTP, NO file write/delete, NO rotation apply.
Payload and sent_scope share the same snapshot to prevent race conditions.
"""

import json as _json
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime as _dt, timezone as _tz
from pathlib import Path
from typing import Any, Optional

from kso_sidecar_agent.pop_pending_lock import (
    try_acquire_pop_pending_lock,
    release_pop_pending_lock,
    PopPendingLockResult,
    FORBIDDEN_SUBSTRINGS,
)
from kso_sidecar_agent.pop_pickup import (
    POP_PENDING_DIR,
    POP_JSONL_FILE,
    CLASS_ELIGIBLE,
    CLASS_DRAFT,
    CLASS_DIAGNOSTIC,
    CLASS_QUARANTINE,
    CLASS_INVALID,
    _validate_record,
    classify_pop_event,
)
from kso_sidecar_agent.pop_payload import (
    PopPayloadEvent,
    PopPayloadEnvelope,
)
from kso_sidecar_agent.pop_rotation_materializer import (
    PopRotationSentScope,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

DEFAULT_MAX_LINES = 10000

# ── Safe reasons ─────────────────────────────────────────────────────

REASON_BUILT = "built"
REASON_NO_PENDING_FILE = "no_pending_file"
REASON_NO_ELIGIBLE_EVENTS = "no_eligible_events"
REASON_LOCK_UNAVAILABLE = "lock_unavailable"
REASON_LIMITED = "limited"
REASON_READ_FAILED = "read_failed"
REASON_PAYLOAD_FAILED = "payload_failed"
REASON_INVALID_RESULT = "invalid_result"

ALLOWED_REASONS = frozenset({
    REASON_BUILT,
    REASON_NO_PENDING_FILE,
    REASON_NO_ELIGIBLE_EVENTS,
    REASON_LOCK_UNAVAILABLE,
    REASON_LIMITED,
    REASON_READ_FAILED,
    REASON_PAYLOAD_FAILED,
    REASON_INVALID_RESULT,
})


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return _dt.now(_tz.utc).isoformat()


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


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopSendPackageResult:
    """Safe result of building a send package from one pending snapshot.

    Contains safe aggregates. Internal payload and sent_scope are
    hidden (repr=False) — never exposed in output, logs, or repr.

    Never contains raw JSON, payload body, line numbers list, file paths,
    filenames, manifest_item_id, device_event_id, batch_id, campaign_id,
    creative_id, sha256, exception text, stacktrace, or secrets.
    """

    status: str = STATUS_OK                    # ok | warning | error
    package_built: bool = False
    lock_acquired: bool = False
    pending_lines_read: int = 0
    eligible_events: int = 0
    payload_events: int = 0
    scope_lines: int = 0
    reason: str = REASON_NO_PENDING_FILE

    # ── Internal-only (repr=False — never exposed) ────────────────────
    _payload: Optional[PopPayloadEnvelope] = field(default=None, repr=False)
    _sent_scope: Optional[PopRotationSentScope] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.status not in (STATUS_OK, STATUS_WARNING, STATUS_ERROR):
            raise ValueError(f"Invalid status '{self.status}'")
        if self.reason not in ALLOWED_REASONS:
            raise ValueError(
                f"Invalid reason '{self.reason}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_REASONS))}"
            )

    def __repr__(self) -> str:
        return (
            f"PopSendPackageResult(status={self.status!r}, "
            f"package_built={self.package_built}, "
            f"lock_acquired={self.lock_acquired}, "
            f"pending_lines_read={self.pending_lines_read}, "
            f"eligible_events={self.eligible_events}, "
            f"payload_events={self.payload_events}, "
            f"scope_lines={self.scope_lines}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def build_pop_send_package(
    root,
    max_lines: int = DEFAULT_MAX_LINES,
) -> PopSendPackageResult:
    """Build an in-memory send package from ONE pending snapshot under lock.

    Pipeline:
        1. Validate max_lines
        2. Acquire pop/pending lock
        3. Read pending snapshot
        4. For each eligible completed event:
           - build PopPayloadEvent (manifest mapping)
           - track line_number → sent scope
        5. Build PopPayloadEnvelope (batch_id + events)
        6. Build PopRotationSentScope from tracked line numbers
        7. Release lock
        8. Return safe PopSendPackageResult

    A single snapshot guarantees: payload and sent_scope share the SAME
    pending line numbers — no race between payload build and scope tracking.

    NO backend send, NO HTTP, NO file write/delete, NO rotation apply.
    Pending file NOT modified.

    Args:
        root: Agent root path (str or Path).
        max_lines: Max pending lines to read (default 10000). <= 0 → error.

    Returns:
        PopSendPackageResult — always safe, never raises.
    """
    # ── Validate max_lines ───────────────────────────────────────
    if not isinstance(max_lines, int) or max_lines <= 0:
        return PopSendPackageResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESULT,
        )

    root = Path(root)

    # ── Acquire lock ─────────────────────────────────────────────
    lock_result = try_acquire_pop_pending_lock(root)

    if not lock_result.acquired:
        return PopSendPackageResult(
            status=STATUS_WARNING,
            reason=REASON_LOCK_UNAVAILABLE,
        )

    try:
        return _build_under_lock(root, lock_result, max_lines)
    finally:
        release_pop_pending_lock(lock_result)


def _build_under_lock(
    root: Path,
    lock_result: PopPendingLockResult,
    max_lines: int,
) -> PopSendPackageResult:
    """Core package builder — called with lock held."""

    jsonl_path = root / POP_PENDING_DIR / POP_JSONL_FILE

    # ── No pending file → empty ok ───────────────────────────────
    if not jsonl_path.exists() or not jsonl_path.is_file():
        return PopSendPackageResult(
            status=STATUS_OK,
            lock_acquired=True,
            reason=REASON_NO_PENDING_FILE,
        )

    # ── Load manifest for mapping ────────────────────────────────
    manifest_data: Optional[dict] = None
    manifest_items: Optional[list] = None
    try:
        from kso_sidecar_agent.manifest_store import read_current_manifest
        manifest_data = read_current_manifest(root)
        manifest_items = manifest_data.get("items", [])
    except Exception:
        manifest_data = None
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

    # ── Read pending snapshot ────────────────────────────────────
    try:
        raw = jsonl_path.read_text(encoding="utf-8")
    except Exception:
        return PopSendPackageResult(
            status=STATUS_ERROR,
            lock_acquired=True,
            reason=REASON_READ_FAILED,
        )

    lines = raw.split("\n")
    now = _now_iso()

    result = PopSendPackageResult(
        lock_acquired=True,
        reason=REASON_NO_ELIGIBLE_EVENTS,
    )

    envelope = PopPayloadEnvelope(
        batch_id=_gen_uuid(),
        sent_at=now,
        events=[],
    )

    scope_line_numbers: list[int] = []
    pending_lines_read = 0
    eligible_events = 0
    limited = False

    for line_content in lines:
        stripped = line_content.strip()
        if not stripped:
            continue

        pending_lines_read += 1

        # ── max_lines limit ──────────────────────────────────
        if pending_lines_read > max_lines:
            limited = True
            break

        # ── Parse ────────────────────────────────────────────
        try:
            record = _json.loads(stripped)
        except Exception:
            continue

        if not isinstance(record, dict):
            continue

        # ── Validate schema ──────────────────────────────────
        if _validate_record(record) is not None:
            continue

        # ── Classify ─────────────────────────────────────────
        classification = classify_pop_event(
            record,
            manifest_items=manifest_items,
            media_cache_complete=media_cache_complete,
        )

        # Only eligible completed events go into the package
        if classification.classification != CLASS_ELIGIBLE:
            continue

        eligible_events += 1

        # ── Manifest mapping ─────────────────────────────────
        selected_order = record.get("selected_order")
        manifest_item = _find_manifest_item(manifest_items, selected_order) if isinstance(selected_order, int) else None

        if manifest_item is None:
            # Mapping lost — skip (should not happen, classify checks this)
            continue

        # ── Build payload event ──────────────────────────────
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
        )

        envelope.events.append(payload_event)

        # ── Track line number for sent scope ─────────────────
        scope_line_numbers.append(pending_lines_read)

    # ── Populate result ──────────────────────────────────────────
    result.pending_lines_read = pending_lines_read
    result.eligible_events = eligible_events
    result.payload_events = len(envelope.events)

    if limited:
        result.status = STATUS_WARNING
        result.reason = REASON_LIMITED
        result.lock_acquired = True
        return result

    if envelope.events:
        # Build sent scope from the same snapshot line numbers
        sent_scope = PopRotationSentScope(_line_numbers=frozenset(scope_line_numbers))
        result._sent_scope = sent_scope
        result._payload = envelope
        result.scope_lines = sent_scope.size
        result.package_built = True
        result.status = STATUS_OK
        result.reason = REASON_BUILT
    else:
        # No eligible events went into payload
        result.status = STATUS_OK
        result.reason = REASON_NO_ELIGIBLE_EVENTS

    return result


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_send_package_result(result: PopSendPackageResult) -> str:
    """Return a safe aggregated string of the send package result.

    Never prints payload body, line numbers list, file paths, filenames,
    manifest_item_id, device_event_id, batch_id, campaign_id, creative_id,
    sha256, exception text, stacktrace, or secrets.
    """
    lines = [
        f"status:                  {result.status}",
        f"package_built:           {str(result.package_built).lower()}",
        f"lock_acquired:           {str(result.lock_acquired).lower()}",
        f"pending_lines_read:      {result.pending_lines_read}",
        f"eligible_events:         {result.eligible_events}",
        f"payload_events:          {result.payload_events}",
        f"scope_lines:             {result.scope_lines}",
        f"reason:                  {result.reason}",
    ]

    output = "\n".join(lines)

    # Safety scan
    lower = output.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise ValueError(
                f"Safe output contains forbidden substring '{fb}'"
            )

    return output
