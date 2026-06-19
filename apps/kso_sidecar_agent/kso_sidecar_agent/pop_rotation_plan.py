"""KSO Sidecar PoP Local Rotation Plan Core — in-memory rotation plan.

Builds an in-memory classification plan for pop/pending/player_events.jsonl:
  - Classifies every line (draft/diagnostic/invalid/eligible)
  - Plans future moves: sent, quarantine, dry_run, failed
  - Uses the same lock as player writer
  - NEVER writes, moves, or deletes files

No actual rotation, no HTTP, no backend, no secret reading.
"""

import json as _json
from copy import deepcopy as _deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from kso_sidecar_agent.pop_pending_lock import (
    try_acquire_pop_pending_lock,
    release_pop_pending_lock,
    PopPendingLockResult,
    STATUS_LOCKED as LOCK_STATUS_LOCKED,
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
    SCAN_OK,
    SCAN_WARNING,
    SCAN_ERROR,
    _validate_record,
    classify_pop_event,
    PopPickupClassification,
)

# ── Local fallback for send runner types (avoid circular import) ─────
# PopSendRunResult fields accessed via duck typing: run_status, pending_should_remain, reason

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

PLAN_OK = "ok"
PLAN_WARNING = "warning"
PLAN_ERROR = "error"

DEFAULT_MAX_LINES = 10000

# ── Safe plan reasons ─────────────────────────────────────────────────

REASON_PLANNED = "planned"
REASON_NO_PENDING_FILE = "no_pending_file"
REASON_LOCK_UNAVAILABLE = "lock_unavailable"
REASON_PENDING_SHOULD_REMAIN = "pending_should_remain"
REASON_DUPLICATE_PENDING_REMAINS = "duplicate_pending_remains"
REASON_SEND_NOT_SUCCESSFUL = "send_not_successful"
REASON_INVALID_LINES_PRESENT = "invalid_lines_present"
REASON_PLAN_LIMITED = "plan_limited"
REASON_READ_FAILED = "read_failed"
REASON_INVALID_RESULT = "invalid_result"

ALLOWED_PLAN_REASONS = frozenset({
    REASON_PLANNED,
    REASON_NO_PENDING_FILE,
    REASON_LOCK_UNAVAILABLE,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_SEND_NOT_SUCCESSFUL,
    REASON_INVALID_LINES_PRESENT,
    REASON_PLAN_LIMITED,
    REASON_READ_FAILED,
    REASON_INVALID_RESULT,
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopRotationPlanResult:
    """Safe in-memory rotation plan result.

    Never contains raw JSON, file paths, payload body, batch_id,
    device_event_id, manifest_item_id, campaign_id, filename,
    sha256, paths, or secrets.
    """

    rotation_status: str = PLAN_WARNING      # ok | warning | error
    pending_lines_before: int = 0
    pending_lines_after: int = 0
    sent_lines: int = 0
    quarantine_lines: int = 0
    dry_run_lines: int = 0
    failed_lines: int = 0
    invalid_lines: int = 0
    pending_untouched: bool = True
    lock_acquired: bool = False
    plan_limited: bool = False
    max_lines: int = DEFAULT_MAX_LINES
    reason: str = REASON_NO_PENDING_FILE

    def __post_init__(self) -> None:
        if self.rotation_status not in (PLAN_OK, PLAN_WARNING, PLAN_ERROR):
            raise ValueError(f"Invalid rotation_status '{self.rotation_status}'")
        if self.reason not in ALLOWED_PLAN_REASONS:
            raise ValueError(
                f"Invalid reason '{self.reason}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_PLAN_REASONS))}"
            )

    def __repr__(self) -> str:
        return (
            f"PopRotationPlanResult(rotation_status={self.rotation_status!r}, "
            f"pending_lines_before={self.pending_lines_before}, "
            f"pending_lines_after={self.pending_lines_after}, "
            f"sent_lines={self.sent_lines}, "
            f"quarantine_lines={self.quarantine_lines}, "
            f"dry_run_lines={self.dry_run_lines}, "
            f"failed_lines={self.failed_lines}, "
            f"invalid_lines={self.invalid_lines}, "
            f"pending_untouched={self.pending_untouched}, "
            f"lock_acquired={self.lock_acquired}, "
            f"plan_limited={self.plan_limited}, "
            f"max_lines={self.max_lines}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Plan builder
# ══════════════════════════════════════════════════════════════════════

def build_pop_rotation_plan(
    root,
    send_run_result: Optional[Any] = None,
    max_lines: int = DEFAULT_MAX_LINES,
) -> PopRotationPlanResult:
    """Build an in-memory rotation plan for pop/pending/player_events.jsonl.

    Pipeline:
        1. Try to acquire lock via try_acquire_pop_pending_lock()
        2. If lock unavailable → return warning, lock_unavailable
        3. Read JSONL line by line
        4. Classify each line via pop_pickup
        5. Plan future destinations based on send_run_result
        6. Release lock
        7. Return safe aggregated PopRotationPlanResult

    NEVER writes, moves, or deletes files — plan only.

    Args:
        root: Agent root path (str or Path).
        send_run_result: Optional PopSendRunResult from a prior backend send.
            If None or pending_should_remain=True → no sent_lines planned.
        max_lines: Max lines to read (default 10000). <= 0 → error.

    Returns:
        PopRotationPlanResult — always safe, never raises.
    """
    # ── Validate max_lines ───────────────────────────────────────
    if not isinstance(max_lines, int) or max_lines <= 0:
        return PopRotationPlanResult(
            rotation_status=PLAN_ERROR,
            pending_untouched=True,
            reason=REASON_INVALID_RESULT,
        )

    root = Path(root)

    # ── Try lock ─────────────────────────────────────────────────
    lock_result = try_acquire_pop_pending_lock(root)
    lock_acquired = lock_result.acquired

    if not lock_acquired:
        return PopRotationPlanResult(
            rotation_status=PLAN_WARNING,
            pending_untouched=True,
            max_lines=max_lines,
            reason=REASON_LOCK_UNAVAILABLE,
        )

    try:
        result = _build_plan_under_lock(root, send_run_result, max_lines)
        result.lock_acquired = True
        return result
    finally:
        release_pop_pending_lock(lock_result)


def _build_plan_under_lock(
    root: Path,
    send_run_result,
    max_lines: int,
) -> PopRotationPlanResult:
    """Core plan logic — called with lock held."""

    jsonl_path = root / POP_PENDING_DIR / POP_JSONL_FILE

    # ── File missing → empty ok ──────────────────────────────────
    if not jsonl_path.exists() or not jsonl_path.is_file():
        return PopRotationPlanResult(
            rotation_status=PLAN_OK,
            pending_untouched=True,
            max_lines=max_lines,
            reason=REASON_NO_PENDING_FILE,
        )

    # ── Determine send policy ───────────────────────────────────
    send_ok = _send_ok(send_run_result)
    send_pending_should_remain = _pending_should_remain(send_run_result)
    is_duplicate = _is_duplicate_batch(send_run_result)

    # If pending_should_remain → no sent_lines allowed
    can_plan_sent = send_ok and not send_pending_should_remain and not is_duplicate

    # ── Load manifest for classification ────────────────────────
    manifest_items = None
    media_cache_complete = None
    try:
        from kso_sidecar_agent.manifest_store import read_current_manifest
        manifest_data = read_current_manifest(root)
        manifest_items = manifest_data.get("items", [])
    except Exception:
        manifest_items = None

    try:
        from kso_sidecar_agent.media_cache import media_cache_status
        mc_status = media_cache_status(root, manifest_items=manifest_items)
        items_total = mc_status.get("items_total", 0)
        items_cached = mc_status.get("items_cached", 0)
        media_cache_complete = (items_total > 0 and items_cached == items_total)
    except Exception:
        media_cache_complete = None

    # ── Read JSONL ──────────────────────────────────────────────
    try:
        raw = jsonl_path.read_text(encoding="utf-8")
    except Exception:
        return PopRotationPlanResult(
            rotation_status=PLAN_ERROR,
            pending_untouched=True,
            max_lines=max_lines,
            reason=REASON_READ_FAILED,
        )

    lines = raw.split("\n")
    plan = PopRotationPlanResult(
        max_lines=max_lines,
        reason=REASON_PLANNED,
    )

    line_number = 0
    for line_content in lines:
        stripped = line_content.strip()
        if not stripped:
            continue

        line_number += 1
        plan.pending_lines_before += 1

        # ── max_lines limit ──────────────────────────────────
        if line_number > max_lines:
            plan.plan_limited = True
            plan.pending_lines_after += 1  # stays in pending
            continue

        # ── Parse ────────────────────────────────────────────
        try:
            record = _json.loads(stripped)
        except Exception:
            plan.invalid_lines += 1
            plan.quarantine_lines += 1
            continue

        if not isinstance(record, dict):
            plan.invalid_lines += 1
            plan.quarantine_lines += 1
            continue

        # ── Validate ─────────────────────────────────────────
        if _validate_record(record) is not None:
            plan.invalid_lines += 1
            plan.quarantine_lines += 1
            continue

        # ── Classify (work on copy — classify mutates) ──────
        record_copy = _deepcopy(record)
        classification = classify_pop_event(
            record_copy,
            manifest_items=manifest_items,
            media_cache_complete=media_cache_complete,
        )

        cls = classification.classification
        event_status = record.get("event_status", "")
        event_type = record.get("event_type", "")

        # ── Route to destination ─────────────────────────────
        if cls == CLASS_INVALID:
            plan.invalid_lines += 1
            plan.quarantine_lines += 1
            continue

        if cls == CLASS_DRAFT or event_status == "draft":
            plan.dry_run_lines += 1
            continue

        if cls == CLASS_DIAGNOSTIC or event_status in ("blocked", "failed"):
            plan.dry_run_lines += 1
            continue

        if cls == CLASS_QUARANTINE:
            plan.quarantine_lines += 1
            continue

        # CLASS_ELIGIBLE: completed + idle + manifest + media
        if cls == CLASS_ELIGIBLE:
            if can_plan_sent:
                plan.sent_lines += 1
            else:
                # stays in pending
                plan.pending_lines_after += 1
            continue

        # Fallback: unknown classification → quarantine
        plan.quarantine_lines += 1

    # ── Calculate pending_lines_after ───────────────────────────
    # pending_lines_after = lines staying in pending (not routed elsewhere)
    # plus lines beyond max_lines
    # We've already been adding to pending_lines_after for non-sent eligible events
    # Total from pending = sent + quarantine + dry_run + pending_after
    # pending_after = pending_before - sent - quarantine - dry_run + plan_limited extras

    # Recalculate: pending_lines_after = total lines - routed lines
    routed = plan.sent_lines + plan.quarantine_lines + plan.dry_run_lines + plan.failed_lines
    # invalid_lines are already counted in quarantine_lines above
    plan.pending_lines_after = plan.pending_lines_before - routed

    # ── Determine status ────────────────────────────────────────
    if is_duplicate:
        plan.rotation_status = PLAN_WARNING
        plan.reason = REASON_DUPLICATE_PENDING_REMAINS
        plan.pending_untouched = True
    elif plan.plan_limited:
        plan.rotation_status = PLAN_WARNING
        plan.reason = REASON_PLAN_LIMITED
        plan.pending_untouched = True
    elif send_pending_should_remain:
        plan.rotation_status = PLAN_WARNING
        plan.reason = REASON_PENDING_SHOULD_REMAIN
        plan.pending_untouched = True
    elif plan.invalid_lines > 0:
        plan.rotation_status = PLAN_WARNING
        plan.reason = REASON_INVALID_LINES_PRESENT
        plan.pending_untouched = True
    elif plan.plan_limited:
        plan.rotation_status = PLAN_WARNING
        plan.reason = REASON_PLAN_LIMITED
        plan.pending_untouched = True
    elif plan.sent_lines > 0 and can_plan_sent:
        plan.rotation_status = PLAN_OK
        plan.reason = REASON_PLANNED
        plan.pending_untouched = False
    elif plan.pending_lines_before == 0:
        plan.rotation_status = PLAN_OK
        plan.reason = REASON_NO_PENDING_FILE
        plan.pending_untouched = True
    else:
        plan.rotation_status = PLAN_WARNING
        plan.reason = REASON_SEND_NOT_SUCCESSFUL
        plan.pending_untouched = True

    return plan


# ══════════════════════════════════════════════════════════════════════
# Send result helpers (duck-typed — no hard import of runner module)
# ══════════════════════════════════════════════════════════════════════

def _send_ok(send_run_result) -> bool:
    """Check if send run result indicates success."""
    if send_run_result is None:
        return False
    return getattr(send_run_result, "run_status", "") == "ok"


def _pending_should_remain(send_run_result) -> bool:
    """Check if pending should remain untouched."""
    if send_run_result is None:
        return True
    return bool(getattr(send_run_result, "pending_should_remain", True))


def _is_duplicate_batch(send_run_result) -> bool:
    """Check if the send result was a 409 duplicate batch."""
    if send_run_result is None:
        return False
    reason = getattr(send_run_result, "reason", "")
    return "duplicate" in str(reason).lower()


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_rotation_plan_result(result: PopRotationPlanResult) -> str:
    """Return a safe aggregated string of the rotation plan.

    Never prints raw JSON, file paths, payload body, IDs,
    filename, sha256, paths, or secrets.
    """
    lines = [
        f"rotation_status:         {result.rotation_status}",
        f"pending_lines_before:    {result.pending_lines_before}",
        f"pending_lines_after:     {result.pending_lines_after}",
        f"sent_lines:              {result.sent_lines}",
        f"quarantine_lines:        {result.quarantine_lines}",
        f"dry_run_lines:           {result.dry_run_lines}",
        f"failed_lines:            {result.failed_lines}",
        f"invalid_lines:           {result.invalid_lines}",
        f"pending_untouched:       {str(result.pending_untouched).lower()}",
        f"lock_acquired:           {str(result.lock_acquired).lower()}",
        f"plan_limited:            {str(result.plan_limited).lower()}",
        f"max_lines:               {result.max_lines}",
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
