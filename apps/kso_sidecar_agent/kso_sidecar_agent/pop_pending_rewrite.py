"""KSO Sidecar PoP Pending Rewrite Atomic Helper — safe atomic overwrite of pending JSONL.

Writes validated retained-pending records atomically to:
  pop/pending/player_events.jsonl

REQUIRES caller to already hold the pop/pending lock. This helper:
  - Validates records (no forbidden keys/values)
  - Writes .tmp → flush → fsync → os.replace
  - NEVER acquires or releases the lock
  - NEVER reads existing pending (caller provides records)
  - NEVER creates sent/quarantine/dry_run/failed

Atomic model: .tmp write → flush → fsync → os.replace → fsync dir.
If os.replace fails, original pending stays untouched.
"""

import json as _json
import os as _os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from kso_sidecar_agent.pop_pending_lock import (
    POP_PENDING_DIR,
    FORBIDDEN_SUBSTRINGS,
    PopPendingLockResult,
)

# Local constant — same filename as in pop_pickup.POP_JSONL_FILE
POP_JSONL_FILE = "player_events.jsonl"


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_WRITTEN = "written"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"

REASON_WRITTEN = "written"
REASON_LOCK_REQUIRED = "lock_required"
REASON_UNSAFE_RECORD = "unsafe_record"
REASON_WRITE_FAILED = "write_failed"
REASON_INVALID_ROOT = "invalid_root"

ALLOWED_REASONS = frozenset({
    REASON_WRITTEN,
    REASON_LOCK_REQUIRED,
    REASON_UNSAFE_RECORD,
    REASON_WRITE_FAILED,
    REASON_INVALID_ROOT,
})


# ══════════════════════════════════════════════════════════════════════
# Record validation
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden(text: str) -> bool:
    """Return True if text contains any forbidden substring (case-insensitive)."""
    if not isinstance(text, str):
        return False
    lower = text.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return True
    return False


def _validate_record(record: dict) -> Optional[str]:
    """Check record for forbidden keys or values.

    Returns error string if unsafe, None if safe.
    """
    if not isinstance(record, dict):
        return "Record is not a dict"

    for key in record:
        if _check_forbidden(str(key)):
            return f"Forbidden key: {key}"

    for key, value in record.items():
        if isinstance(value, str):
            if _check_forbidden(value):
                return f"Forbidden value in key '{key}'"
        elif isinstance(value, (int, float, bool, type(None))):
            continue
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str) and _check_forbidden(item):
                    return f"Forbidden value in key '{key}'[{i}]"
                if isinstance(item, dict):
                    inner = _validate_record(item)
                    if inner:
                        return f"Forbidden nested record in '{key}'[{i}]: {inner}"
        elif isinstance(value, dict):
            inner = _validate_record(value)
            if inner:
                return f"Forbidden nested record in '{key}': {inner}"

    return None


def _safe_unlink(path: Path) -> None:
    """Try to remove a file; never raise."""
    try:
        _os.unlink(str(path))
    except (FileNotFoundError, OSError):
        pass


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopPendingRewriteResult:
    """Safe result of an atomic pending file rewrite.

    Never contains file paths, tmp paths, filenames, lock path,
    exception text, raw records, IDs, token, secret, or backend URL.
    """

    status: str = STATUS_ERROR      # written | skipped | error
    written: bool = False
    records_written: int = 0
    line_size_bytes: int = 0
    reason: str = REASON_INVALID_ROOT

    # Internal-only — never exposed in safe output or repr
    _pending_path: Optional[Path] = field(default=None, repr=False)
    _tmp_path: Optional[Path] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.status not in (STATUS_WRITTEN, STATUS_SKIPPED, STATUS_ERROR):
            raise ValueError(f"Invalid status '{self.status}'")
        if self.reason not in ALLOWED_REASONS:
            raise ValueError(
                f"Invalid reason '{self.reason}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_REASONS))}"
            )

    def __repr__(self) -> str:
        return (
            f"PopPendingRewriteResult(status={self.status!r}, "
            f"written={self.written}, "
            f"records_written={self.records_written}, "
            f"line_size_bytes={self.line_size_bytes}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def rewrite_pending_pop_events_atomic(
    root,
    records: List[dict],
    lock_result: Optional[PopPendingLockResult] = None,
) -> PopPendingRewriteResult:
    """Atomically rewrite pop/pending/player_events.jsonl with validated records.

    REQUIRES caller to already hold the pop/pending lock.
    This helper does NOT acquire or release the lock — it only verifies.

    Pipeline:
        1. Validate root
        2. Verify lock_result is present and acquired
        3. Validate each record (dict, no forbidden keys/values, JSON serializable)
        4. Create pop/pending/ directory
        5. Write .tmp file with JSONL content
        6. flush + fsync .tmp
        7. os.replace(.tmp → player_events.jsonl)
        8. fsync directory (best-effort)
        9. Return safe PopPendingRewriteResult

    If os.replace fails, original pending stays untouched.
    NEVER creates sent/quarantine/dry_run/failed.
    NEVER does HTTP. NEVER reads secrets.

    Args:
        root: Agent root path (str or Path).
        records: List of validated dict records to write.
            Empty list is allowed — creates empty pending file.
        lock_result: PopPendingLockResult from try_acquire_pop_pending_lock().
            Must have acquired=True.

    Returns:
        PopPendingRewriteResult — always safe, never raises.
    """
    # ── Validate root ────────────────────────────────────────────
    if root is None:
        return PopPendingRewriteResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ROOT,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return PopPendingRewriteResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ROOT,
        )

    # ── Verify lock ──────────────────────────────────────────────
    if lock_result is None:
        return PopPendingRewriteResult(
            status=STATUS_SKIPPED,
            reason=REASON_LOCK_REQUIRED,
        )

    if not isinstance(lock_result, PopPendingLockResult):
        return PopPendingRewriteResult(
            status=STATUS_SKIPPED,
            reason=REASON_LOCK_REQUIRED,
        )

    if not lock_result.acquired:
        return PopPendingRewriteResult(
            status=STATUS_SKIPPED,
            reason=REASON_LOCK_REQUIRED,
        )

    # ── Validate each record ─────────────────────────────────────
    valid_records = []
    for rec in records:
        if not isinstance(rec, dict):
            return PopPendingRewriteResult(
                status=STATUS_ERROR,
                reason=REASON_UNSAFE_RECORD,
            )

        err = _validate_record(rec)
        if err:
            return PopPendingRewriteResult(
                status=STATUS_ERROR,
                reason=REASON_UNSAFE_RECORD,
            )

        try:
            line = _json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n"
        except (TypeError, ValueError):
            return PopPendingRewriteResult(
                status=STATUS_ERROR,
                reason=REASON_UNSAFE_RECORD,
            )

        valid_records.append(line)

    # ── Build paths ──────────────────────────────────────────────
    dir_path = root / POP_PENDING_DIR
    pending_path = dir_path / POP_JSONL_FILE
    tmp_path = dir_path / f".{POP_JSONL_FILE}.tmp"

    total_bytes = 0
    fd = -1

    try:
        # ── Ensure directory exists ──────────────────────────────
        dir_path.mkdir(parents=True, exist_ok=True)

        # ── Write .tmp ───────────────────────────────────────────
        content = "".join(valid_records)
        total_bytes = len(content.encode("utf-8"))

        tmp_path.write_text(content, encoding="utf-8")

        # ── flush + fsync ────────────────────────────────────────
        fd = _os.open(str(tmp_path), _os.O_RDWR)
        try:
            _os.fsync(fd)
        finally:
            _os.close(fd)
            fd = -1

        # ── Atomic replace ───────────────────────────────────────
        _os.replace(str(tmp_path), str(pending_path))

        # ── fsync directory (best-effort) ────────────────────────
        try:
            dir_fd = _os.open(str(dir_path), _os.O_RDONLY)
            try:
                _os.fsync(dir_fd)
            finally:
                _os.close(dir_fd)
        except OSError:
            pass

        return PopPendingRewriteResult(
            status=STATUS_WRITTEN,
            written=True,
            records_written=len(valid_records),
            line_size_bytes=total_bytes,
            reason=REASON_WRITTEN,
            _pending_path=pending_path,
        )

    except Exception:
        # ── Cleanup tmp on any failure ───────────────────────────
        if fd >= 0:
            try:
                _os.close(fd)
            except OSError:
                pass

        _safe_unlink(tmp_path)

        # Do NOT expose exception text or stacktrace
        return PopPendingRewriteResult(
            status=STATUS_ERROR,
            reason=REASON_WRITE_FAILED,
        )


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_pending_rewrite_result(result: PopPendingRewriteResult) -> str:
    """Return a safe aggregated string of the pending rewrite result.

    Never prints file paths, tmp paths, filenames, lock path,
    exception text, raw records, IDs, token, secret, or backend URL.
    """
    lines = [
        f"status:               {result.status}",
        f"written:              {str(result.written).lower()}",
        f"records_written:      {result.records_written}",
        f"line_size_bytes:      {result.line_size_bytes}",
        f"reason:               {result.reason}",
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
