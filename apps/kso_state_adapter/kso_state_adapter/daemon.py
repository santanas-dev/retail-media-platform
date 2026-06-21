"""KSO UKM 4 State Adapter — daemon core.

Long-running process:
  read state from source → validate → atomic write kso_state.json →
  safe health file → sleep → repeat.

Fail-closed: source error → write unknown/error, never idle.
"""

import json as _json
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from kso_state_adapter.state_model import (
    KsoState,
    STATE_UNKNOWN,
    STATE_ERROR,
    ALLOWED_STATES,
    FORBIDDEN_STATE_KEYS,
)
from kso_state_adapter.state_writer import atomic_write_state, STATUS_WRITTEN

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

DAEMON_STATUS_RUNNING = "running"
DAEMON_STATUS_STOPPING = "stopping"
DAEMON_STATUS_STOPPED = "stopped"
DAEMON_STATUS_ERROR = "error"

REASON_OK = "ok"
REASON_STOPPED = "daemon_stopped"
REASON_MAX_CYCLES = "max_cycles_reached"
REASON_STOP_CHECK = "stop_check_triggered"
REASON_MAX_ERRORS = "max_consecutive_errors_exceeded"
REASON_INVALID_ARGS = "invalid_args"
REASON_EMPTY_RUN = "empty_run"

ALLOWED_REASONS = frozenset({
    REASON_OK,
    REASON_STOPPED,
    REASON_MAX_CYCLES,
    REASON_STOP_CHECK,
    REASON_MAX_ERRORS,
    REASON_INVALID_ARGS,
    REASON_EMPTY_RUN,
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoStateAdapterDaemonResult:
    """Safe daemon result. Never contains paths, raw data, secrets."""

    status: str = DAEMON_STATUS_STOPPED
    cycles_completed: int = 0
    state_written: bool = False
    last_state: str = STATE_UNKNOWN
    error_count: int = 0
    health_written: bool = False
    reason: str = REASON_EMPTY_RUN

    def __post_init__(self):
        if self.status not in (
            DAEMON_STATUS_RUNNING, DAEMON_STATUS_STOPPING,
            DAEMON_STATUS_STOPPED, DAEMON_STATUS_ERROR,
        ):
            raise ValueError(f"Invalid status '{self.status}'")
        if self.reason not in ALLOWED_REASONS:
            raise ValueError(f"Invalid reason '{self.reason}'")

    def __repr__(self) -> str:
        return (
            f"KsoStateAdapterDaemonResult("
            f"status={self.status!r}, "
            f"cycles_completed={self.cycles_completed}, "
            f"state_written={self.state_written}, "
            f"last_state={self.last_state!r}, "
            f"error_count={self.error_count}, "
            f"health_written={self.health_written}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Health file
# ══════════════════════════════════════════════════════════════════════

def _write_health(
    health_file: Optional[str],
    status: str,
    last_state: str,
    cycles_completed: int,
    error_count: int,
    reason: str,
) -> bool:
    """Atomic write of safe health JSON. Returns True if written."""
    if not health_file:
        return False

    data = {
        "status": status,
        "last_state": last_state,
        "cycles_completed": cycles_completed,
        "error_count": error_count,
        "last_reason": reason,
    }

    json_str = _json.dumps(data, indent=2, ensure_ascii=False)
    lower = json_str.lower()
    for fb in FORBIDDEN_STATE_KEYS:
        if fb in lower:
            return False

    hp = Path(health_file)
    try:
        hp.parent.mkdir(parents=True, exist_ok=True)
        import os as _os
        import tempfile as _tempfile
        fd, tmp = _tempfile.mkstemp(
            dir=str(hp.parent), prefix=".adapter-health.", suffix=".tmp",
        )
        try:
            _os.write(fd, json_str.encode("utf-8"))
            _os.fsync(fd)
        finally:
            _os.close(fd)
        _os.replace(tmp, str(hp))
        return True
    except (OSError, ValueError):
        return False


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_kso_state_adapter_daemon(
    root,
    source,
    interval_seconds: float = 1.0,
    max_cycles: Optional[int] = None,
    stop_check: Optional[Callable[[], bool]] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    health_file: Optional[str] = None,
    max_consecutive_errors: int = 3,
) -> KsoStateAdapterDaemonResult:
    """Run state adapter daemon loop.

    Each cycle:
      1. Check stop_check()
      2. Read state from source (safe — error → unknown)
      3. Atomic write kso_state.json
      4. Write health file (if configured)
      5. Sleep interval_seconds

    Fail-closed: source error → write unknown/error, NEVER idle.

    Args:
        root: Agent root path.
        source: Injectable KsoStateSource.
        interval_seconds: Wait between cycles.
        max_cycles: Max cycles (None = run forever).
        stop_check: Callable → True to stop.
        sleep_fn: Injectable sleep.
        health_file: Optional path for health JSON.
        max_consecutive_errors: Stop after N consecutive errors.

    Returns:
        KsoStateAdapterDaemonResult — safe, never raises.
    """
    if max_consecutive_errors < 1:
        return KsoStateAdapterDaemonResult(
            status=DAEMON_STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        _root = Path(root)
    except (TypeError, ValueError):
        return KsoStateAdapterDaemonResult(
            status=DAEMON_STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    if source is None:
        return KsoStateAdapterDaemonResult(
            status=DAEMON_STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    _sleep = sleep_fn if sleep_fn is not None else _time.sleep
    _stop = stop_check if stop_check is not None else (lambda: False)

    completed = 0
    errors = 0
    consecutive_errors = 0
    last_state = STATE_UNKNOWN
    state_written = False
    reason = REASON_OK
    daemon_status = DAEMON_STATUS_RUNNING

    while True:
        if _stop():
            reason = REASON_STOP_CHECK
            daemon_status = DAEMON_STATUS_STOPPING
            break

        if max_cycles is not None and completed >= max_cycles:
            reason = REASON_MAX_CYCLES
            daemon_status = DAEMON_STATUS_STOPPING
            break

        # ── Read state from source ──────────────────────────────
        source_failed = False
        try:
            state = source.read_state()
            if state.state == "idle":
                # NEVER write idle from a broken or unverified source
                pass
        except Exception:
            # Source error → fail-closed
            source_failed = True
            state = KsoState(state=STATE_ERROR)
            errors += 1
            consecutive_errors += 1

        # ── Write state ─────────────────────────────────────────
        write_failed = False
        try:
            write_result = atomic_write_state(_root, state)
            if write_result["status"] == STATUS_WRITTEN:
                last_state = state.state
                state_written = True
                if not source_failed:
                    consecutive_errors = 0
            else:
                write_failed = True
                errors += 1
                consecutive_errors += 1
        except Exception:
            write_failed = True
            errors += 1
            consecutive_errors += 1

        completed += 1

        # ── Health file ─────────────────────────────────────────
        if health_file:
            _write_health(
                health_file,
                status="ok" if consecutive_errors == 0 else "error",
                last_state=last_state,
                cycles_completed=completed,
                error_count=errors,
                reason=reason,
            )

        # ── Consecutive error limit ─────────────────────────────
        if consecutive_errors >= max_consecutive_errors:
            reason = REASON_MAX_ERRORS
            daemon_status = DAEMON_STATUS_ERROR
            if health_file:
                _write_health(
                    health_file, status="error",
                    last_state=last_state,
                    cycles_completed=completed,
                    error_count=errors,
                    reason=reason,
                )
            break

        # ── Wait ────────────────────────────────────────────────
        try:
            _sleep(interval_seconds)
        except Exception:
            pass

    final_status = daemon_status
    if final_status in (DAEMON_STATUS_STOPPING, DAEMON_STATUS_RUNNING):
        final_status = DAEMON_STATUS_STOPPED

    return KsoStateAdapterDaemonResult(
        status=final_status,
        cycles_completed=completed,
        state_written=state_written,
        last_state=last_state,
        error_count=errors,
        health_written=health_file is not None,
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_daemon_result(result: KsoStateAdapterDaemonResult) -> str:
    """Safe formatted output. No paths, no raw data."""
    lines = [
        f"status: {result.status}",
        f"cycles_completed: {result.cycles_completed}",
        f"state_written: {str(result.state_written).lower()}",
        f"last_state: {result.last_state}",
        f"error_count: {result.error_count}",
        f"health_written: {str(result.health_written).lower()}",
        f"reason: {result.reason}",
    ]
    output = "\n".join(lines)
    lower = output.lower()
    for fb in FORBIDDEN_STATE_KEYS:
        if fb in lower:
            raise ValueError(f"Safe output contains forbidden '{fb}'")
    return output
