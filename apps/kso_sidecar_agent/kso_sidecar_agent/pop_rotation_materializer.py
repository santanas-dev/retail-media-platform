"""KSO Sidecar PoP Rotation Materializer Core — in-memory bucket builder.

Reads pop/pending/player_events.jsonl under lock, classifies every line,
and produces in-memory buckets for future atomic writes:
  - retained_pending (stays in pending)
  - sent (backend-confirmed eligible events)
  - quarantine (unsafe/schema/invalid events)
  - dry_run (draft/diagnostic events)
  - failed (retry-exhausted events)

NEVER writes files. NEVER calls write_pop_rotation_records_atomic.
NEVER modifies/deletes pending. No HTTP, no backend, no secret reading.
"""

import json as _json
from copy import deepcopy as _deepcopy
from dataclasses import dataclass, field
from datetime import datetime as _dt, timezone as _tz
from pathlib import Path
from typing import Any, List, Optional, Tuple

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

# ── Local fallback for send runner types (duck typing) ──────────────────
# PopSendRunResult: run_status, pending_should_remain, reason


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

DEFAULT_MAX_LINES = 10000

# ── Safe reasons ─────────────────────────────────────────────────────

REASON_MATERIALIZED = "materialized"
REASON_NO_PENDING_FILE = "no_pending_file"
REASON_LOCK_UNAVAILABLE = "lock_unavailable"
REASON_LOCK_REQUIRED = "lock_required"
REASON_PENDING_SHOULD_REMAIN = "pending_should_remain"
REASON_DUPLICATE_PENDING_REMAINS = "duplicate_pending_remains"
REASON_SEND_NOT_SUCCESSFUL = "send_not_successful"
REASON_INVALID_LINES_PRESENT = "invalid_lines_present"
REASON_LIMITED = "limited"
REASON_READ_FAILED = "read_failed"
REASON_INVALID_RESULT = "invalid_result"

ALLOWED_REASONS = frozenset({
    REASON_MATERIALIZED,
    REASON_NO_PENDING_FILE,
    REASON_LOCK_UNAVAILABLE,
    REASON_LOCK_REQUIRED,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_SEND_NOT_SUCCESSFUL,
    REASON_INVALID_LINES_PRESENT,
    REASON_LIMITED,
    REASON_READ_FAILED,
    REASON_INVALID_RESULT,
})

# ── Sanitized record types ──────────────────────────────────────────

RECORD_TYPE_SENT = "rotation_sent"
RECORD_TYPE_QUARANTINE = "rotation_quarantine"
RECORD_TYPE_DRY_RUN = "rotation_dry_run"
RECORD_TYPE_FAILED = "rotation_failed"

ALLOWED_RECORD_TYPES = frozenset({
    RECORD_TYPE_SENT,
    RECORD_TYPE_QUARANTINE,
    RECORD_TYPE_DRY_RUN,
    RECORD_TYPE_FAILED,
})

# ── Bucket reasons ───────────────────────────────────────────────────

BUCKET_REASON_DRAFT = "draft_not_pop"
BUCKET_REASON_BLOCKED = "blocked_not_pop"
BUCKET_REASON_FAILED = "failed_not_pop"
BUCKET_REASON_INVALID_JSON = "invalid_json"
BUCKET_REASON_FORBIDDEN_FIELD = "forbidden_field"
BUCKET_REASON_UNKNOWN = "unknown_classification"


# ══════════════════════════════════════════════════════════════════════
# Sanitized record builder
# ══════════════════════════════════════════════════════════════════════

def _sanitized_rotation_record(
    record_type: str,
    reason: str,
    line_number: Optional[int] = None,
) -> dict:
    """Build a sanitized rotation record.

    Never contains raw JSON, IDs, paths, secrets, or forbidden substrings.
    """
    if record_type not in ALLOWED_RECORD_TYPES:
        raise ValueError(
            f"Invalid record_type '{record_type}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_RECORD_TYPES))}"
        )

    now = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    r: dict = {
        "schema_version": 1,
        "record_type": record_type,
        "reason": reason,
        "created_at": now,
        "source": "player_events",
    }

    if line_number is not None:
        r["line_number"] = line_number

    # Safety check: no forbidden substrings anywhere
    for key, value in r.items():
        if isinstance(value, str):
            lower = value.lower()
            for fb in FORBIDDEN_SUBSTRINGS:
                if fb in lower:
                    raise ValueError(
                        f"Sanitized record value for '{key}' contains forbidden '{fb}'"
                    )

    return r


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopRotationMaterializeResult:
    """Safe in-memory materialization result with internal record buckets.

    The public fields are safe aggregates. Internal _* buckets contain the
    actual records for the next step (rotation apply) but are never exposed
    in repr, str, or safe output.

    Never contains raw JSON, file paths, payload body, IDs, token,
    backend URL, paths, or secrets.
    """

    status: str = STATUS_OK                    # ok | warning | error
    pending_lines_before: int = 0
    retained_pending_records: int = 0
    sent_records: int = 0
    quarantine_records: int = 0
    dry_run_records: int = 0
    failed_records: int = 0
    invalid_lines: int = 0
    lock_acquired: bool = False
    pending_untouched: bool = True
    materialized: bool = False
    max_lines: int = DEFAULT_MAX_LINES
    limited: bool = False
    reason: str = REASON_NO_PENDING_FILE

    # ── Internal buckets (repr=False — never exposed) ─────────────────

    _retained_pending_records: List[dict] = field(default_factory=list, repr=False)
    _sent_records: List[dict] = field(default_factory=list, repr=False)
    _quarantine_records: List[dict] = field(default_factory=list, repr=False)
    _dry_run_records: List[dict] = field(default_factory=list, repr=False)
    _failed_records: List[dict] = field(default_factory=list, repr=False)

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
            f"PopRotationMaterializeResult(status={self.status!r}, "
            f"pending_lines_before={self.pending_lines_before}, "
            f"retained_pending_records={self.retained_pending_records}, "
            f"sent_records={self.sent_records}, "
            f"quarantine_records={self.quarantine_records}, "
            f"dry_run_records={self.dry_run_records}, "
            f"failed_records={self.failed_records}, "
            f"invalid_lines={self.invalid_lines}, "
            f"lock_acquired={self.lock_acquired}, "
            f"pending_untouched={self.pending_untouched}, "
            f"materialized={self.materialized}, "
            f"max_lines={self.max_lines}, "
            f"limited={self.limited}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Send result helpers (duck-typed)
# ══════════════════════════════════════════════════════════════════════

def _send_ok(send_run_result) -> bool:
    if send_run_result is None:
        return False
    return getattr(send_run_result, "run_status", "") == "ok"


def _pending_should_remain(send_run_result) -> bool:
    if send_run_result is None:
        return True
    return bool(getattr(send_run_result, "pending_should_remain", True))


def _is_duplicate_batch(send_run_result) -> bool:
    if send_run_result is None:
        return False
    reason = getattr(send_run_result, "reason", "")
    return "duplicate" in str(reason).lower()


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def materialize_pop_rotation_records(
    root,
    send_run_result: Optional[Any] = None,
    max_lines: int = DEFAULT_MAX_LINES,
) -> PopRotationMaterializeResult:
    """Build in-memory materialization buckets from pending player events.

    Convenience wrapper that acquires lock, materializes, and releases lock.

    Pipeline:
        1. Validate max_lines
        2. Try to acquire lock via try_acquire_pop_pending_lock()
        3. If lock unavailable → warning, lock_unavailable
        4. Call materialize_pop_rotation_records_locked()
        5. Release lock in finally
        6. Return safe PopRotationMaterializeResult

    NEVER writes, moves, or deletes files. NEVER calls atomic writer.
    NEVER does HTTP. NEVER reads secrets.
    """
    # ── Validate max_lines ───────────────────────────────────────
    if not isinstance(max_lines, int) or max_lines <= 0:
        return PopRotationMaterializeResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESULT,
        )

    root = Path(root)

    # ── Try lock ─────────────────────────────────────────────────
    lock_result = try_acquire_pop_pending_lock(root)

    if not lock_result.acquired:
        return PopRotationMaterializeResult(
            status=STATUS_WARNING,
            pending_untouched=True,
            max_lines=max_lines,
            reason=REASON_LOCK_UNAVAILABLE,
        )

    try:
        return materialize_pop_rotation_records_locked(
            root, lock_result, send_run_result, max_lines)
    finally:
        release_pop_pending_lock(lock_result)


def materialize_pop_rotation_records_locked(
    root,
    lock_result: PopPendingLockResult,
    send_run_result: Optional[Any] = None,
    max_lines: int = DEFAULT_MAX_LINES,
) -> PopRotationMaterializeResult:
    """Build in-memory materialization buckets under an already-held lock.

    REQUIRES caller to already hold the pop/pending lock.
    This function does NOT acquire or release the lock.

    Pipeline:
        1. Validate lock_result (acquired=True required)
        2. Validate max_lines
        3. Read pop/pending/player_events.jsonl
        4. Validate and classify each line
        5. Build in-memory buckets: retained_pending, sent, quarantine, dry_run, failed
        6. Return safe PopRotationMaterializeResult

    NEVER writes, moves, or deletes files. NEVER calls atomic writer.
    NEVER calls pending rewrite. NEVER acquires/releases lock.
    NEVER does HTTP. NEVER reads secrets.
    """
    # ── Validate lock ────────────────────────────────────────────
    if lock_result is None:
        return PopRotationMaterializeResult(
            status=STATUS_WARNING,
            pending_untouched=True,
            max_lines=max_lines,
            reason=REASON_LOCK_REQUIRED,
        )

    if not isinstance(lock_result, PopPendingLockResult):
        return PopRotationMaterializeResult(
            status=STATUS_WARNING,
            pending_untouched=True,
            max_lines=max_lines,
            reason=REASON_LOCK_REQUIRED,
        )

    if not lock_result.acquired:
        return PopRotationMaterializeResult(
            status=STATUS_WARNING,
            pending_untouched=True,
            max_lines=max_lines,
            reason=REASON_LOCK_REQUIRED,
        )

    # ── Validate max_lines ───────────────────────────────────────
    if not isinstance(max_lines, int) or max_lines <= 0:
        return PopRotationMaterializeResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESULT,
            pending_untouched=True,
        )

    root = Path(root)

    result = _materialize_under_lock(root, send_run_result, max_lines)
    result.lock_acquired = True  # Lock was already held by caller
    return result


def _materialize_under_lock(
    root: Path,
    send_run_result,
    max_lines: int,
) -> PopRotationMaterializeResult:
    """Core materialization logic — called with lock held."""

    jsonl_path = root / POP_PENDING_DIR / POP_JSONL_FILE

    # ── File missing → empty ok ──────────────────────────────────
    if not jsonl_path.exists() or not jsonl_path.is_file():
        return PopRotationMaterializeResult(
            status=STATUS_OK,
            pending_untouched=True,
            max_lines=max_lines,
            reason=REASON_NO_PENDING_FILE,
        )

    # ── Determine send policy ────────────────────────────────────
    send_ok = _send_ok(send_run_result)
    send_pr = _pending_should_remain(send_run_result)
    is_dup = _is_duplicate_batch(send_run_result)
    can_sent = send_ok and not send_pr and not is_dup

    # ── Load manifest for classification ─────────────────────────
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

    # ── Read JSONL ───────────────────────────────────────────────
    try:
        raw = jsonl_path.read_text(encoding="utf-8")
    except Exception:
        return PopRotationMaterializeResult(
            status=STATUS_ERROR,
            pending_untouched=True,
            max_lines=max_lines,
            reason=REASON_READ_FAILED,
        )

    lines = raw.split("\n")
    result = PopRotationMaterializeResult(
        max_lines=max_lines,
        reason=REASON_MATERIALIZED,
        materialized=True,
    )

    line_number = 0
    for line_content in lines:
        stripped = line_content.strip()
        if not stripped:
            continue

        line_number += 1
        result.pending_lines_before += 1

        # ── max_lines limit ──────────────────────────────────
        if line_number > max_lines:
            result.limited = True
            result._retained_pending_records.append({})  # placeholder — stays in pending
            continue

        # ── Parse ────────────────────────────────────────────
        try:
            record = _json.loads(stripped)
        except Exception:
            result.invalid_lines += 1
            result._quarantine_records.append(
                _sanitized_rotation_record(
                    RECORD_TYPE_QUARANTINE,
                    BUCKET_REASON_INVALID_JSON,
                    line_number=line_number,
                )
            )
            continue

        if not isinstance(record, dict):
            result.invalid_lines += 1
            result._quarantine_records.append(
                _sanitized_rotation_record(
                    RECORD_TYPE_QUARANTINE,
                    BUCKET_REASON_INVALID_JSON,
                    line_number=line_number,
                )
            )
            continue

        # ── Validate schema ──────────────────────────────────
        if _validate_record(record) is not None:
            result.invalid_lines += 1
            result._quarantine_records.append(
                _sanitized_rotation_record(
                    RECORD_TYPE_QUARANTINE,
                    BUCKET_REASON_FORBIDDEN_FIELD,
                    line_number=line_number,
                )
            )
            continue

        # ── Classify ─────────────────────────────────────────
        record_copy = _deepcopy(record)
        classification = classify_pop_event(
            record_copy,
            manifest_items=manifest_items,
            media_cache_complete=media_cache_complete,
        )

        cls = classification.classification
        event_status = record.get("event_status", "")
        event_type = record.get("event_type", "")

        # ── Route to bucket ──────────────────────────────────
        if cls == CLASS_INVALID:
            result.invalid_lines += 1
            result._quarantine_records.append(
                _sanitized_rotation_record(
                    RECORD_TYPE_QUARANTINE,
                    BUCKET_REASON_INVALID_JSON,
                    line_number=line_number,
                )
            )

        elif cls == CLASS_DRAFT or event_status == "draft":
            result._dry_run_records.append(
                _sanitized_rotation_record(
                    RECORD_TYPE_DRY_RUN,
                    BUCKET_REASON_DRAFT,
                    line_number=line_number,
                )
            )

        elif cls == CLASS_DIAGNOSTIC or event_status in ("blocked", "failed"):
            reason = BUCKET_REASON_BLOCKED if event_status == "blocked" else BUCKET_REASON_FAILED
            result._dry_run_records.append(
                _sanitized_rotation_record(
                    RECORD_TYPE_DRY_RUN,
                    reason,
                    line_number=line_number,
                )
            )

        elif cls == CLASS_QUARANTINE:
            result._quarantine_records.append(
                _sanitized_rotation_record(
                    RECORD_TYPE_QUARANTINE,
                    BUCKET_REASON_UNKNOWN,
                    line_number=line_number,
                )
            )

        elif cls == CLASS_ELIGIBLE:
            if can_sent:
                # Keep the original safe record (already validated)
                result._sent_records.append(dict(record))
            else:
                result._retained_pending_records.append(dict(record))

        else:
            # Unknown classification → quarantine
            result._quarantine_records.append(
                _sanitized_rotation_record(
                    RECORD_TYPE_QUARANTINE,
                    BUCKET_REASON_UNKNOWN,
                    line_number=line_number,
                )
            )

    # ── Populate aggregate counts ────────────────────────────────
    result.sent_records = len(result._sent_records)
    result.quarantine_records = len(result._quarantine_records)
    result.dry_run_records = len(result._dry_run_records)
    result.failed_records = len(result._failed_records)
    result.retained_pending_records = len(result._retained_pending_records)

    # ── Determine status ─────────────────────────────────────────
    if is_dup:
        result.status = STATUS_WARNING
        result.reason = REASON_DUPLICATE_PENDING_REMAINS
        result.pending_untouched = True
    elif result.limited:
        result.status = STATUS_WARNING
        result.reason = REASON_LIMITED
        result.pending_untouched = True
    elif send_pr:
        result.status = STATUS_WARNING
        result.reason = REASON_PENDING_SHOULD_REMAIN
        result.pending_untouched = True
    elif result.invalid_lines > 0:
        result.status = STATUS_WARNING
        result.reason = REASON_INVALID_LINES_PRESENT
        result.pending_untouched = True
    elif result.sent_records > 0 and can_sent:
        result.status = STATUS_OK
        result.reason = REASON_MATERIALIZED
        result.pending_untouched = False
    elif result.pending_lines_before == 0:
        result.status = STATUS_OK
        result.reason = REASON_NO_PENDING_FILE
        result.pending_untouched = True
    else:
        result.status = STATUS_WARNING
        result.reason = REASON_SEND_NOT_SUCCESSFUL
        result.pending_untouched = True

    return result


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_rotation_materialize_result(result: PopRotationMaterializeResult) -> str:
    """Return a safe aggregated string of the materialization result.

    Never prints raw JSON, file paths, IDs, filenames, sha256,
    paths, secrets, or bucket contents.
    """
    lines = [
        f"status:                      {result.status}",
        f"pending_lines_before:        {result.pending_lines_before}",
        f"retained_pending_records:    {result.retained_pending_records}",
        f"sent_records:                {result.sent_records}",
        f"quarantine_records:          {result.quarantine_records}",
        f"dry_run_records:             {result.dry_run_records}",
        f"failed_records:              {result.failed_records}",
        f"invalid_lines:               {result.invalid_lines}",
        f"lock_acquired:               {str(result.lock_acquired).lower()}",
        f"pending_untouched:           {str(result.pending_untouched).lower()}",
        f"materialized:                {str(result.materialized).lower()}",
        f"max_lines:                   {result.max_lines}",
        f"limited:                     {str(result.limited).lower()}",
        f"reason:                      {result.reason}",
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
