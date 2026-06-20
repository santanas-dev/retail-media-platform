"""KSO Sidecar PoP Local Rotation Apply Core — full rotation cycle under one lock.

Orchestrates the complete rotation pipeline:
  1. acquire lock
  2. materialize_pop_rotation_records_locked() — read + classify
  3. write_pop_rotation_records_atomic() — sent/quarantine/dry_run/failed
  4. rewrite_pending_pop_events_atomic() — retained pending only
  5. release lock

Sent bucket only if backend-confirmed (send_run_result ok + pending_should_remain=false).
If any step fails: pending untouched. Lock released in finally.
No HTTP, no backend send, no secret reading.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from kso_sidecar_agent.pop_pending_lock import (
    try_acquire_pop_pending_lock,
    release_pop_pending_lock,
    FORBIDDEN_SUBSTRINGS,
)
from kso_sidecar_agent.pop_rotation_materializer import (
    materialize_pop_rotation_records_locked,
    PopRotationMaterializeResult,
    STATUS_OK as MAT_OK,
    STATUS_WARNING as MAT_WARNING,
    STATUS_ERROR as MAT_ERROR,
    REASON_LOCK_UNAVAILABLE,
    REASON_LOCK_REQUIRED,
)
from kso_sidecar_agent.pop_rotation_files import (
    write_pop_rotation_records_atomic,
    STATUS_WRITTEN as FW_WRITTEN,
)
from kso_sidecar_agent.pop_pending_rewrite import (
    rewrite_pending_pop_events_atomic,
    STATUS_WRITTEN as PRW_WRITTEN,
)


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

DEFAULT_MAX_LINES = 10000

# ── Safe reasons ─────────────────────────────────────────────────────

REASON_APPLIED = "applied"
REASON_NO_PENDING_FILE = "no_pending_file"
REASON_LOCK_UNAVAILABLE = "lock_unavailable"
REASON_LOCK_REQUIRED = "lock_required"
REASON_MATERIALIZE_FAILED = "materialize_failed"
REASON_TARGET_WRITE_FAILED = "target_write_failed"
REASON_PENDING_REWRITE_FAILED = "pending_rewrite_failed"
REASON_PENDING_SHOULD_REMAIN = "pending_should_remain"
REASON_DUPLICATE_PENDING_REMAINS = "duplicate_pending_remains"
REASON_SEND_NOT_SUCCESSFUL = "send_not_successful"
REASON_LIMITED = "limited"
REASON_INVALID_RESULT = "invalid_result"

ALLOWED_REASONS = frozenset({
    REASON_APPLIED,
    REASON_NO_PENDING_FILE,
    REASON_LOCK_UNAVAILABLE,
    REASON_LOCK_REQUIRED,
    REASON_MATERIALIZE_FAILED,
    REASON_TARGET_WRITE_FAILED,
    REASON_PENDING_REWRITE_FAILED,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_DUPLICATE_PENDING_REMAINS,
    REASON_SEND_NOT_SUCCESSFUL,
    REASON_LIMITED,
    REASON_INVALID_RESULT,
})

# ── Target order (sent first, then quarantine/dry_run/failed) ────────

TARGET_ORDER = ("sent", "quarantine", "dry_run", "failed")

# Mapping from materializer bucket to target
BUCKET_TARGET_MAP = {
    "_sent_records": "sent",
    "_quarantine_records": "quarantine",
    "_dry_run_records": "dry_run",
    "_failed_records": "failed",
}


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopRotationApplyResult:
    """Safe result of a full local rotation apply cycle.

    Never contains file paths, filenames, raw records, payload body,
    IDs, token, secret, backend URL, or stacktrace.
    """

    status: str = STATUS_ERROR             # ok | warning | error
    applied: bool = False
    pending_untouched: bool = True
    lock_acquired: bool = False
    pending_lines_before: int = 0
    pending_lines_after: int = 0
    sent_records: int = 0
    quarantine_records: int = 0
    dry_run_records: int = 0
    failed_records: int = 0
    invalid_lines: int = 0
    target_files_written: int = 0
    pending_rewritten: bool = False
    reason: str = REASON_INVALID_RESULT

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
            f"PopRotationApplyResult(status={self.status!r}, "
            f"applied={self.applied}, "
            f"pending_untouched={self.pending_untouched}, "
            f"lock_acquired={self.lock_acquired}, "
            f"pending_lines_before={self.pending_lines_before}, "
            f"pending_lines_after={self.pending_lines_after}, "
            f"sent_records={self.sent_records}, "
            f"quarantine_records={self.quarantine_records}, "
            f"dry_run_records={self.dry_run_records}, "
            f"failed_records={self.failed_records}, "
            f"invalid_lines={self.invalid_lines}, "
            f"target_files_written={self.target_files_written}, "
            f"pending_rewritten={self.pending_rewritten}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def apply_pop_rotation_local(
    root,
    send_run_result: Optional[Any] = None,
    sent_scope = None,
    max_lines: int = DEFAULT_MAX_LINES,
) -> PopRotationApplyResult:
    """Execute a full local rotation cycle under one lock.

    Pipeline:
        1. acquire lock
        2. materialize_pop_rotation_records_locked() — build in-memory buckets
        3. write_pop_rotation_records_atomic() — write sent/quarantine/dry_run/failed
           (only non-empty buckets)
        4. rewrite_pending_pop_events_atomic() — updated retained_pending
        5. release lock in finally

    Sent only if send_run_result confirms: run_status=ok, pending_should_remain=false.
    If any target write fails → pending untouched, return error.
    If pending rewrite fails → target files may exist, but pending untouched.

    Args:
        root: Agent root path (str or Path).
        send_run_result: Optional PopSendRunResult from a prior backend send.
        max_lines: Max lines to read (default 10000). <= 0 → error.

    Returns:
        PopRotationApplyResult — always safe, never raises.
    """
    # ── Validate max_lines ───────────────────────────────────────
    if not isinstance(max_lines, int) or max_lines <= 0:
        return PopRotationApplyResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESULT,
        )

    root = Path(root)

    # ── Acquire lock ─────────────────────────────────────────────
    lock_result = try_acquire_pop_pending_lock(root)

    if not lock_result.acquired:
        return PopRotationApplyResult(
            status=STATUS_WARNING,
            pending_untouched=True,
            reason=REASON_LOCK_UNAVAILABLE,
        )

    result = PopRotationApplyResult(lock_acquired=True)

    try:
        # ── 1. Materialize ───────────────────────────────────────
        mat_result = materialize_pop_rotation_records_locked(
            root, lock_result, send_run_result, sent_scope, max_lines)

        result.pending_lines_before = mat_result.pending_lines_before
        result.invalid_lines = mat_result.invalid_lines

        # Materialize critical failure → abort
        if mat_result.status == MAT_ERROR:
            result.status = STATUS_ERROR
            result.reason = REASON_MATERIALIZE_FAILED
            result.pending_untouched = True
            return result

        # No pending file or empty → nothing to do, considered applied
        if not mat_result.materialized or mat_result.pending_lines_before == 0:
            result.status = STATUS_OK
            result.reason = REASON_NO_PENDING_FILE
            result.applied = True
            return result

        # ── 2. Write target buckets (sent first) ─────────────────
        buckets = {
            "sent": list(mat_result._sent_records),
            "quarantine": list(mat_result._quarantine_records),
            "dry_run": list(mat_result._dry_run_records),
            "failed": list(mat_result._failed_records),
        }

        files_written = 0

        for target in TARGET_ORDER:
            records = buckets.get(target, [])

            # ── Safety gate for sent ─────────────────────────
            if target == "sent" and not records:
                result.sent_records = 0
                continue

            if target == "sent":
                result.sent_records = len(records)
            elif target == "quarantine":
                result.quarantine_records = len(records)
            elif target == "dry_run":
                result.dry_run_records = len(records)
            elif target == "failed":
                result.failed_records = len(records)

            # Skip empty buckets
            if not records:
                continue

            fw_result = write_pop_rotation_records_atomic(root, target, records)

            if fw_result.status == FW_WRITTEN:
                files_written += 1
            else:
                # Target write failed → abort, pending untouched
                result.status = STATUS_ERROR
                result.reason = REASON_TARGET_WRITE_FAILED
                result.pending_untouched = True
                result.target_files_written = files_written
                return result

        result.target_files_written = files_written

        # ── 3. Rewrite pending (only retained records) ───────────
        retained = list(mat_result._retained_pending_records)
        prw_result = rewrite_pending_pop_events_atomic(
            root, retained, lock_result=lock_result)

        if prw_result.status == PRW_WRITTEN:
            result.pending_rewritten = True
            result.pending_lines_after = len(retained)
            result.pending_untouched = False
        else:
            # Pending rewrite failed — target files may exist
            result.status = STATUS_ERROR
            result.reason = REASON_PENDING_REWRITE_FAILED
            result.pending_untouched = True
            return result

        # ── 4. Success ───────────────────────────────────────────
        result.status = STATUS_OK
        result.reason = REASON_APPLIED
        result.applied = True
        return result

    except Exception:
        # Catch-all: pending untouched
        result.status = STATUS_ERROR
        result.reason = REASON_MATERIALIZE_FAILED
        result.pending_untouched = True
        return result

    finally:
        release_pop_pending_lock(lock_result)


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_rotation_apply_result(result: PopRotationApplyResult) -> str:
    """Return a safe aggregated string of the rotation apply result.

    Never prints file paths, filenames, raw records, payload body,
    IDs, token, secret, backend URL, or stacktrace.
    """
    lines = [
        f"status:                   {result.status}",
        f"applied:                  {str(result.applied).lower()}",
        f"pending_untouched:        {str(result.pending_untouched).lower()}",
        f"lock_acquired:            {str(result.lock_acquired).lower()}",
        f"pending_lines_before:     {result.pending_lines_before}",
        f"pending_lines_after:      {result.pending_lines_after}",
        f"sent_records:             {result.sent_records}",
        f"quarantine_records:       {result.quarantine_records}",
        f"dry_run_records:          {result.dry_run_records}",
        f"failed_records:           {result.failed_records}",
        f"invalid_lines:            {result.invalid_lines}",
        f"target_files_written:     {result.target_files_written}",
        f"pending_rewritten:        {str(result.pending_rewritten).lower()}",
        f"reason:                   {result.reason}",
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
