"""KSO Sidecar PoP Rotation Atomic File Ops — safe JSONL writing for rotation targets.

Writes validated records atomically to:
  pop/sent/        — backend-confirmed events
  pop/quarantine/  — unsafe/schema/mismatch events
  pop/dry_run/     — draft/diagnostic events (not PoP)
  pop/failed/      — retry-exhausted events

Atomic model: .tmp write → flush → fsync → os.replace → fsync dir.
NEVER reads, modifies, or deletes pending. No HTTP, no backend, no secrets.

This is a low-level helper. Actual rotation orchestration uses it later.
"""

import json as _json
import os as _os
import time as _time
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime as _dt, timezone as _tz
from pathlib import Path
from typing import Any, List, Optional


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

POP_BASE = "pop"

ALLOWED_TARGETS = frozenset({"sent", "quarantine", "dry_run", "failed"})

# ── Write status ─────────────────────────────────────────────────────

STATUS_WRITTEN = "written"
STATUS_SKIPPED = "skipped"
STATUS_ERROR = "error"

# ── Safe reasons ──────────────────────────────────────────────────────

REASON_WRITTEN = "written"
REASON_NO_RECORDS = "no_records"
REASON_INVALID_TARGET = "invalid_target"
REASON_UNSAFE_RECORD = "unsafe_record"
REASON_WRITE_FAILED = "write_failed"
REASON_INVALID_ROOT = "invalid_root"

ALLOWED_REASONS = frozenset({
    REASON_WRITTEN,
    REASON_NO_RECORDS,
    REASON_INVALID_TARGET,
    REASON_UNSAFE_RECORD,
    REASON_WRITE_FAILED,
    REASON_INVALID_ROOT,
})

# ── Forbidden substrings (same contract as pop_pending_lock) ──────────

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

# ── File naming ───────────────────────────────────────────────────────

ROTATION_FILE_PREFIX = "rotation_"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PopRotationFileWriteResult:
    """Safe result of an atomic rotation file write.

    Never contains file paths, tmp paths, filenames, exception text,
    raw records, IDs, token, secret, backend URL, paths, or sha256.
    """

    status: str = STATUS_ERROR        # written | skipped | error
    written: bool = False
    target: Optional[str] = None      # sent | quarantine | dry_run | failed | None
    records_written: int = 0
    line_size_bytes: int = 0
    reason: str = REASON_INVALID_ROOT

    # Internal-only — never exposed in safe output or repr
    _target_path: Optional[Path] = field(default=None, repr=False)
    _tmp_path: Optional[Path] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.status not in (STATUS_WRITTEN, STATUS_SKIPPED, STATUS_ERROR):
            raise ValueError(f"Invalid status '{self.status}'")
        if self.reason not in ALLOWED_REASONS:
            raise ValueError(
                f"Invalid reason '{self.reason}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_REASONS))}"
            )
        if self.target is not None and self.target not in ALLOWED_TARGETS:
            raise ValueError(
                f"Invalid target '{self.target}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_TARGETS))}"
            )

    def __repr__(self) -> str:
        return (
            f"PopRotationFileWriteResult(status={self.status!r}, "
            f"written={self.written}, target={self.target!r}, "
            f"records_written={self.records_written}, "
            f"line_size_bytes={self.line_size_bytes}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════

def _safe_unlink(path: Path) -> None:
    """Try to remove a file; never raise."""
    try:
        _os.unlink(str(path))
    except (FileNotFoundError, OSError):
        pass


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

    # Check keys
    for key in record:
        if _check_forbidden(str(key)):
            return f"Forbidden key: {key}"

    # Check values
    for key, value in record.items():
        if isinstance(value, str):
            if _check_forbidden(value):
                return f"Forbidden value in key '{key}'"
        elif isinstance(value, (int, float, bool, type(None))):
            continue  # scalars OK
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


def _ts_utc() -> str:
    """Return compact UTC timestamp: YYYYMMDDThhmmssZ."""
    return _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def write_pop_rotation_records_atomic(
    root,
    target: str,
    records: List[dict],
    now: Optional[str] = None,
) -> PopRotationFileWriteResult:
    """Write safe records to a rotation target directory using atomic JSONL.

    Pipeline:
        1. Validate target (sent | quarantine | dry_run | failed)
        2. If no records → skipped / no_records
        3. Validate each record (no forbidden keys/values, must be dict, must serialize)
        4. Create pop/<target>/ directory
        5. Write .tmp file with JSONL content (one record per line, \\n terminated)
        6. flush + fsync
        7. os.replace(.tmp → rotation_<utc>.jsonl)
        8. fsync directory (best-effort)
        9. Return safe PopRotationFileWriteResult

    NEVER reads pending. NEVER does HTTP. NEVER reads secrets.

    Args:
        root: Agent root path (str or Path).
        target: One of "sent", "quarantine", "dry_run", "failed".
        records: List of validated dict records to write.
        now: Optional UTC timestamp string (for deterministic naming in tests).

    Returns:
        PopRotationFileWriteResult — always safe, never raises.
    """
    # ── Validate root ────────────────────────────────────────────
    if root is None:
        return PopRotationFileWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ROOT,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return PopRotationFileWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ROOT,
        )

    # ── Validate target ──────────────────────────────────────────
    if target not in ALLOWED_TARGETS:
        return PopRotationFileWriteResult(
            status=STATUS_SKIPPED,
            target=None,
            reason=REASON_INVALID_TARGET,
        )

    # ── No records → skip ────────────────────────────────────────
    if not records:
        return PopRotationFileWriteResult(
            status=STATUS_SKIPPED,
            target=target,
            reason=REASON_NO_RECORDS,
        )

    # ── Validate each record ─────────────────────────────────────
    valid_records = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            return PopRotationFileWriteResult(
                status=STATUS_ERROR,
                target=target,
                reason=REASON_UNSAFE_RECORD,
            )

        # Validate forbidden
        err = _validate_record(rec)
        if err:
            return PopRotationFileWriteResult(
                status=STATUS_ERROR,
                target=target,
                reason=REASON_UNSAFE_RECORD,
            )

        # Verify JSON serializable
        try:
            line = _json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n"
        except (TypeError, ValueError):
            return PopRotationFileWriteResult(
                status=STATUS_ERROR,
                target=target,
                reason=REASON_UNSAFE_RECORD,
            )

        valid_records.append(line)

    if not valid_records:
        return PopRotationFileWriteResult(
            status=STATUS_SKIPPED,
            target=target,
            reason=REASON_NO_RECORDS,
        )

    # ── Build paths ──────────────────────────────────────────────
    ts = now if now else _ts_utc()
    dir_path = root / POP_BASE / target

    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return PopRotationFileWriteResult(
            status=STATUS_ERROR,
            target=target,
            reason=REASON_WRITE_FAILED,
        )

    target_name = f"{ROTATION_FILE_PREFIX}{ts}.jsonl"
    target_path = dir_path / target_name
    tmp_path = dir_path / f".{target_name}.tmp"

    total_bytes = 0
    fd = -1

    try:
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

        # ── Atomic rename ────────────────────────────────────────
        _os.replace(str(tmp_path), str(target_path))

        # ── fsync directory (best-effort) ────────────────────────
        try:
            dir_fd = _os.open(str(dir_path), _os.O_RDONLY)
            try:
                _os.fsync(dir_fd)
            finally:
                _os.close(dir_fd)
        except OSError:
            pass  # best-effort

        return PopRotationFileWriteResult(
            status=STATUS_WRITTEN,
            written=True,
            target=target,
            records_written=len(valid_records),
            line_size_bytes=total_bytes,
            reason=REASON_WRITTEN,
            _target_path=target_path,
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
        return PopRotationFileWriteResult(
            status=STATUS_ERROR,
            target=target,
            reason=REASON_WRITE_FAILED,
        )


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_pop_rotation_file_result(result: PopRotationFileWriteResult) -> str:
    """Return a safe aggregated string of the file write result.

    Never prints file paths, tmp paths, filenames, exception text,
    raw records, IDs, token, secret, backend URL, or stacktrace.
    """
    target_str = str(result.target) if result.target else "None"
    lines = [
        f"status:               {result.status}",
        f"written:              {str(result.written).lower()}",
        f"target:               {target_str}",
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
