"""KSO Sidecar PoP Pending Lock Core — safe file lock for pending events.

Provides lock helpers for future sidecar rotation/pickup.
Uses the SAME lock file as player writer:
  {root}/pop/pending/player_events.lock

Cross-platform atomic lock via os.open(O_CREAT | O_EXCL | O_WRONLY).
No rotation, no move, no delete, no HTTP, no backend.
"""

import json as _json
import hashlib as _hashlib
import os as _os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════════════════════════
# Constants (mirrored from pop_writer.py — same lock contract)
# ══════════════════════════════════════════════════════════════════════

POP_PENDING_DIR = "pop/pending"
POP_LOCK_FILE = "player_events.lock"

# ── Lock marker v2 ──────────────────────────────────────────────────

LOCK_MARKER_SCHEMA = 2
LOCK_COMPONENT = "sidecar"
DEFAULT_LOCK_OPERATION = "unknown"

ALLOWED_LOCK_OPERATIONS = frozenset({
    "rotation_plan",
    "rotation_apply",
    "send_package",
    "pop_write",
    "unknown",
})

# ── Lock status ──────────────────────────────────────────────────────

STATUS_LOCKED = "locked"
STATUS_RELEASED = "released"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"

# ── Lock reasons ─────────────────────────────────────────────────────

REASON_LOCKED = "locked"
REASON_RELEASED = "released"
REASON_LOCK_UNAVAILABLE = "lock_unavailable"
REASON_LOCK_FAILED = "lock_failed"
REASON_RELEASE_FAILED = "release_failed"
REASON_INVALID_ROOT = "invalid_root"

# ── Forbidden substrings (checked in lock marker, result output) ─────

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
    "filename", "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "full_manifest", "media_bytes", "stacktrace",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopPendingLockResult:
    """Safe result of a pop/pending lock operation.

    Never contains absolute paths, lock path, exception text,
    stacktrace, token, secret, backend URL, IDs, filenames, or sha256.
    """

    status: str = STATUS_ERROR             # locked | released | skipped | error
    acquired: bool = False
    released: bool = False
    reason: str = REASON_LOCK_FAILED
    # Internal-only — never exposed in safe output or repr
    _lock_path: Optional[Path] = field(default=None, repr=False)

    def __repr__(self) -> str:
        return (
            f"PopPendingLockResult(status={self.status!r}, "
            f"acquired={self.acquired}, released={self.released}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════

def _get_boot_id_hash() -> str:
    """Read /proc/sys/kernel/random/boot_id, return SHA-256 hex digest.

    Returns empty string if /proc is not available or unreadable.
    Never raises — fail-silent.
    """
    try:
        with open("/proc/sys/kernel/random/boot_id", "r") as fh:
            boot_id = fh.read().strip()
            return _hashlib.sha256(boot_id.encode("utf-8")).hexdigest()
    except (OSError, PermissionError):
        return ""


def _build_lock_marker(operation: str) -> str:
    """Build a safe v2 JSON lock marker for sidecar.

    Args:
        operation: Lock operation name (from ALLOWED_LOCK_OPERATIONS).

    Returns:
        JSON string (one line) suitable for writing into lock file.
    """
    op = operation if operation in ALLOWED_LOCK_OPERATIONS else DEFAULT_LOCK_OPERATION
    marker = {
        "schema_version": LOCK_MARKER_SCHEMA,
        "component": LOCK_COMPONENT,
        "operation": op,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "pid": _os.getpid(),
        "boot_id_hash": _get_boot_id_hash(),
    }
    return _json.dumps(marker, ensure_ascii=False, sort_keys=True) + "\n"


def _safe_unlink(path: Path) -> None:
    """Try to remove a file; never raise."""
    try:
        _os.unlink(str(path))
    except (FileNotFoundError, OSError):
        pass


def _check_forbidden(value: str) -> bool:
    """Return True if value contains any forbidden substring."""
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return True
    return False


def _validate_lock_marker(marker_json: str) -> bool:
    """Ensure the lock marker JSON is safe — no forbidden substrings."""
    return not _check_forbidden(marker_json)


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def try_acquire_pop_pending_lock(root, operation: str = DEFAULT_LOCK_OPERATION) -> PopPendingLockResult:
    """Try to acquire an exclusive lock on pop/pending/player_events.jsonl.

    Uses os.open(..., O_CREAT | O_EXCL | O_WRONLY) for atomic lock creation.
    Same lock file as player writer: {root}/pop/pending/player_events.lock.
    Writes a safe v2 JSON marker (schema_version=2, component=sidecar, operation,
    pid, boot_id_hash).

    Non-blocking: returns immediately if lock is held by another process.

    Args:
        root: Agent root path (str or Path).
        operation: Lock operation name. Must be one of ALLOWED_LOCK_OPERATIONS
                   (rotation_plan, rotation_apply, send_package, pop_write, unknown).
                   Defaults to "unknown". Invalid values are normalised to "unknown".

    Returns:
        PopPendingLockResult — acquired=True if lock obtained, False otherwise.
        Never raises. Lock path never exposed in repr.
    """
    # Validate root
    if root is None:
        return PopPendingLockResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ROOT,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return PopPendingLockResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ROOT,
        )

    pending_dir = root / POP_PENDING_DIR

    # Create directory if missing
    try:
        pending_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return PopPendingLockResult(
            status=STATUS_ERROR,
            reason=REASON_LOCK_FAILED,
        )

    lock_path = pending_dir / POP_LOCK_FILE

    # Try atomic create
    try:
        fd = _os.open(str(lock_path), _os.O_CREAT | _os.O_EXCL | _os.O_WRONLY)
    except (FileExistsError, OSError):
        return PopPendingLockResult(
            status=STATUS_SKIPPED,
            acquired=False,
            reason=REASON_LOCK_UNAVAILABLE,
        )

    # Write safe v2 marker
    try:
        marker_json = _build_lock_marker(operation)
        _os.write(fd, marker_json.encode("utf-8"))
    except OSError:
        _os.close(fd)
        _safe_unlink(lock_path)
        return PopPendingLockResult(
            status=STATUS_ERROR,
            reason=REASON_LOCK_FAILED,
        )

    _os.close(fd)

    return PopPendingLockResult(
        status=STATUS_LOCKED,
        acquired=True,
        reason=REASON_LOCKED,
        _lock_path=lock_path,
    )


def release_pop_pending_lock(lock_result: PopPendingLockResult) -> PopPendingLockResult:
    """Release a previously acquired pop/pending lock.

    Deletes the lock file. Never raises — fail-silent.

    Args:
        lock_result: PopPendingLockResult from try_acquire_pop_pending_lock().

    Returns:
        PopPendingLockResult with status=released or error.
    """
    if not isinstance(lock_result, PopPendingLockResult):
        return PopPendingLockResult(
            status=STATUS_ERROR,
            reason=REASON_RELEASE_FAILED,
        )

    lock_path = lock_result._lock_path

    if lock_path is None or not isinstance(lock_path, Path):
        # Nothing to release
        return PopPendingLockResult(
            status=STATUS_RELEASED,
            released=True,
            reason=REASON_RELEASED,
        )

    try:
        _safe_unlink(lock_path)
    except Exception:
        return PopPendingLockResult(
            status=STATUS_ERROR,
            reason=REASON_RELEASE_FAILED,
        )

    return PopPendingLockResult(
        status=STATUS_RELEASED,
        released=True,
        reason=REASON_RELEASED,
    )


# ══════════════════════════════════════════════════════════════════════
# Context manager (convenience, for future rotation use)
# ══════════════════════════════════════════════════════════════════════

class pop_pending_lock:
    """Context manager for pop/pending lock.

    Usage:
        lock_result = try_acquire_pop_pending_lock(root)
        if not lock_result.acquired:
            return  # skip

        with pop_pending_lock(lock_result):
            # safe read/write with lock held
            pass
        # lock released automatically
    """

    def __init__(self, lock_result: PopPendingLockResult):
        self._lock_result = lock_result
        self._entered = False

    def __enter__(self) -> PopPendingLockResult:
        self._entered = True
        return self._lock_result

    def __exit__(self, exc_type, exc_val, exc_tb):
        release_pop_pending_lock(self._lock_result)
        self._entered = False
        return False  # don't suppress exceptions
