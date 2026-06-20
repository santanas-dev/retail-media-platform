"""KSO Sidecar Stale Lock Detector — safe read-only stale lock check.

Reads the lock marker from pop/pending/player_events.lock and returns a
safe aggregate detection result. NEVER deletes, renames, truncates, or
modifies the lock file or pending data.

This is DETECT-ONLY — cleanup_allowed is always False on this step.
Auto-cleanup will be a future step (27.3.3).

NO backend, NO HTTP, NO auth, NO secret, NO media bytes.
"""

import json as _json
import os as _os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════════════════════════
# Constants (mirrored from pop_pending_lock.py — same lock contract)
# ══════════════════════════════════════════════════════════════════════

POP_PENDING_DIR = "pop/pending"
POP_LOCK_FILE = "player_events.lock"

# ── Status values ───────────────────────────────────────────────────

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

# ── Reasons ─────────────────────────────────────────────────────────

REASON_NO_LOCK = "no_lock"
REASON_FRESH_LOCK = "fresh_lock"
REASON_STALE_DETECTED = "stale_detected"
REASON_CRITICAL_STALE_DETECTED = "critical_stale_detected"
REASON_V1_DETECT_ONLY = "v1_detect_only"
REASON_INVALID_MARKER_DETECT_ONLY = "invalid_marker_detect_only"
REASON_INVALID_ARGS = "invalid_args"
REASON_READ_FAILED = "read_failed"

# ── Age buckets ─────────────────────────────────────────────────────

AGE_FRESH = "fresh"
AGE_STALE = "stale"
AGE_CRITICAL = "critical"
AGE_UNKNOWN = "unknown"

# ── Process status ──────────────────────────────────────────────────

PROC_ALIVE = "alive"
PROC_NOT_ALIVE = "not_alive"
PROC_UNKNOWN = "unknown"
PROC_NOT_CHECKED = "not_checked"

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
    "filename", "manifest_item_id", "device_event_id", "batch_id",
    "campaign_id", "creative_id", "schedule_item_id",
    "sha256", "full_manifest", "media_bytes", "stacktrace",
    "boot_id", "pid",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopStaleLockDetectionResult:
    """Safe result of a stale lock detection check.

    Never contains absolute paths, lock filename, pid, boot_id,
    boot_id_hash, marker JSON, created_at values, or forbidden substrings.
    """

    status: str = STATUS_OK
    lock_present: bool = False
    marker_version: int = 0
    stale_detected: bool = False
    critical: bool = False
    cleanup_allowed: bool = False  # always False on this step
    age_bucket: str = AGE_UNKNOWN
    process_status: str = PROC_NOT_CHECKED
    reason: str = REASON_NO_LOCK
    stale_seconds: int = 0
    critical_seconds: int = 0
    age_seconds: int = 0

    def __repr__(self) -> str:
        return (
            f"PopStaleLockDetectionResult("
            f"status={self.status!r}, "
            f"lock_present={self.lock_present}, "
            f"marker_version={self.marker_version}, "
            f"stale_detected={self.stale_detected}, "
            f"critical={self.critical}, "
            f"cleanup_allowed={self.cleanup_allowed}, "
            f"age_bucket={self.age_bucket!r}, "
            f"process_status={self.process_status!r}, "
            f"reason={self.reason!r}, "
            f"stale_seconds={self.stale_seconds}, "
            f"critical_seconds={self.critical_seconds}, "
            f"age_seconds={self.age_seconds})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden(value: str) -> bool:
    """Return True if value contains any forbidden substring."""
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return True
    return False


def _check_pid_alive(pid: int) -> str:
    """Check if a process with the given pid is alive.

    Returns PROC_ALIVE, PROC_NOT_ALIVE, or PROC_UNKNOWN.
    Never raises — fail-silent.
    """
    try:
        _os.kill(pid, 0)
        return PROC_ALIVE
    except ProcessLookupError:
        return PROC_NOT_ALIVE
    except (PermissionError, OSError):
        return PROC_UNKNOWN


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def detect_pop_pending_lock_staleness(
    root,
    stale_seconds: int = 600,
    critical_seconds: int = 1800,
    now: Optional[datetime] = None,
) -> PopStaleLockDetectionResult:
    """Detect whether the PoP pending lock file is stale.

    Reads the lock marker from {root}/pop/pending/player_events.lock.
    Does NOT delete, rename, truncate, or modify the lock file.
    Does NOT modify pending data.

    Args:
        root: Agent root path (str or Path).
        stale_seconds: Age threshold for stale detection (default: 600 = 10 min).
        critical_seconds: Age threshold for critical alert (default: 1800 = 30 min).
        now: Optional datetime for test time injection. Defaults to UTC now.

    Returns:
        PopStaleLockDetectionResult — safe aggregate, never raises.
    """
    # ── Validate arguments ───────────────────────────────────────
    if stale_seconds <= 0:
        return PopStaleLockDetectionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
        )
    if critical_seconds <= stale_seconds:
        return PopStaleLockDetectionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
        )

    if now is None:
        now = datetime.now(timezone.utc)

    # ── Resolve lock path ─────────────────────────────────────────
    try:
        root = Path(root)
    except (TypeError, ValueError):
        return PopStaleLockDetectionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
        )

    lock_path = root / POP_PENDING_DIR / POP_LOCK_FILE

    # ── Check lock presence ───────────────────────────────────────
    try:
        lock_stat = lock_path.stat()
    except FileNotFoundError:
        return PopStaleLockDetectionResult(
            status=STATUS_OK,
            lock_present=False,
            reason=REASON_NO_LOCK,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
        )
    except OSError:
        return PopStaleLockDetectionResult(
            status=STATUS_ERROR,
            lock_present=True,
            reason=REASON_READ_FAILED,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
        )

    # ── Calculate age ─────────────────────────────────────────────
    mtime = datetime.fromtimestamp(lock_stat.st_mtime, tz=timezone.utc)
    age_seconds = int((now - mtime).total_seconds())
    if age_seconds < 0:
        age_seconds = 0  # clock skew protection

    # ── Read marker ───────────────────────────────────────────────
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return PopStaleLockDetectionResult(
            status=STATUS_ERROR,
            lock_present=True,
            reason=REASON_READ_FAILED,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
            age_seconds=age_seconds,
        )

    # ── Parse marker ──────────────────────────────────────────────
    try:
        marker = _json.loads(raw)
    except (ValueError, TypeError):
        # v1 marker or corrupt — detect-only
        marker_version = 1 if raw == "locked" else 0
        if age_seconds >= critical_seconds:
            age_bucket = AGE_CRITICAL
            return PopStaleLockDetectionResult(
                status=STATUS_WARNING,
                lock_present=True,
                marker_version=marker_version,
                stale_detected=True,
                critical=True,
                cleanup_allowed=False,
                age_bucket=age_bucket,
                process_status=PROC_NOT_CHECKED,
                reason=REASON_INVALID_MARKER_DETECT_ONLY if marker_version == 0 else REASON_V1_DETECT_ONLY,
                stale_seconds=stale_seconds,
                critical_seconds=critical_seconds,
                age_seconds=age_seconds,
            )
        elif age_seconds >= stale_seconds:
            return PopStaleLockDetectionResult(
                status=STATUS_WARNING,
                lock_present=True,
                marker_version=marker_version,
                stale_detected=True,
                critical=False,
                cleanup_allowed=False,
                age_bucket=AGE_STALE,
                process_status=PROC_NOT_CHECKED,
                reason=REASON_INVALID_MARKER_DETECT_ONLY if marker_version == 0 else REASON_V1_DETECT_ONLY,
                stale_seconds=stale_seconds,
                critical_seconds=critical_seconds,
                age_seconds=age_seconds,
            )
        else:
            return PopStaleLockDetectionResult(
                status=STATUS_WARNING,
                lock_present=True,
                marker_version=marker_version,
                stale_detected=False,
                critical=False,
                cleanup_allowed=False,
                age_bucket=AGE_FRESH,
                process_status=PROC_NOT_CHECKED,
                reason=(REASON_INVALID_MARKER_DETECT_ONLY if marker_version == 0 else REASON_V1_DETECT_ONLY),
                stale_seconds=stale_seconds,
                critical_seconds=critical_seconds,
                age_seconds=age_seconds,
            )

    # ── Validate marker schema ────────────────────────────────────
    if not isinstance(marker, dict):
        return PopStaleLockDetectionResult(
            status=STATUS_WARNING,
            lock_present=True,
            marker_version=0,
            stale_detected=age_seconds >= stale_seconds,
            critical=age_seconds >= critical_seconds,
            cleanup_allowed=False,
            age_bucket=AGE_STALE if age_seconds >= stale_seconds else (
                AGE_CRITICAL if age_seconds >= critical_seconds else AGE_FRESH),
            process_status=PROC_NOT_CHECKED,
            reason=REASON_INVALID_MARKER_DETECT_ONLY,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
            age_seconds=age_seconds,
        )

    schema_version = marker.get("schema_version")
    if schema_version != 2:
        # Unknown schema — treat as invalid, detect-only
        return PopStaleLockDetectionResult(
            status=STATUS_WARNING,
            lock_present=True,
            marker_version=schema_version if isinstance(schema_version, int) else 0,
            stale_detected=age_seconds >= stale_seconds,
            critical=age_seconds >= critical_seconds,
            cleanup_allowed=False,
            age_bucket=AGE_STALE if age_seconds >= stale_seconds else (
                AGE_CRITICAL if age_seconds >= critical_seconds else AGE_FRESH),
            process_status=PROC_NOT_CHECKED,
            reason=REASON_INVALID_MARKER_DETECT_ONLY,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
            age_seconds=age_seconds,
        )

    # ── v2 marker — check PID (safe, never exposed) ───────────────
    pid = marker.get("pid")
    if isinstance(pid, int) and pid > 0:
        process_status = _check_pid_alive(pid)
    else:
        process_status = PROC_UNKNOWN

    # ── Determine age bucket and staleness ────────────────────────
    if age_seconds >= critical_seconds:
        age_bucket = AGE_CRITICAL
        return PopStaleLockDetectionResult(
            status=STATUS_WARNING,
            lock_present=True,
            marker_version=2,
            stale_detected=True,
            critical=True,
            cleanup_allowed=False,
            age_bucket=age_bucket,
            process_status=process_status,
            reason=REASON_CRITICAL_STALE_DETECTED if process_status == PROC_NOT_ALIVE else REASON_STALE_DETECTED,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
            age_seconds=age_seconds,
        )
    elif age_seconds >= stale_seconds:
        age_bucket = AGE_STALE
        return PopStaleLockDetectionResult(
            status=STATUS_WARNING,
            lock_present=True,
            marker_version=2,
            stale_detected=True,
            critical=False,
            cleanup_allowed=False,
            age_bucket=age_bucket,
            process_status=process_status,
            reason=REASON_STALE_DETECTED,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
            age_seconds=age_seconds,
        )
    else:
        age_bucket = AGE_FRESH
        return PopStaleLockDetectionResult(
            status=STATUS_OK,
            lock_present=True,
            marker_version=2,
            stale_detected=False,
            critical=False,
            cleanup_allowed=False,
            age_bucket=age_bucket,
            process_status=process_status,
            reason=REASON_FRESH_LOCK,
            stale_seconds=stale_seconds,
            critical_seconds=critical_seconds,
            age_seconds=age_seconds,
        )


def format_pop_stale_lock_detection_result(
    result: PopStaleLockDetectionResult,
) -> str:
    """Format a PopStaleLockDetectionResult as a safe human-readable string.

    Never contains lock path, pid, boot_id, marker JSON, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"lock_present: {str(result.lock_present).lower()}",
        f"marker_version: {result.marker_version}",
        f"stale_detected: {str(result.stale_detected).lower()}",
        f"critical: {str(result.critical).lower()}",
        f"cleanup_allowed: {str(result.cleanup_allowed).lower()}",
        f"age_bucket: {result.age_bucket}",
        f"process_status: {result.process_status}",
        f"reason: {result.reason}",
        f"stale_seconds: {result.stale_seconds}",
        f"critical_seconds: {result.critical_seconds}",
        f"age_seconds: {result.age_seconds}",
    ]
    return "\n".join(lines)
