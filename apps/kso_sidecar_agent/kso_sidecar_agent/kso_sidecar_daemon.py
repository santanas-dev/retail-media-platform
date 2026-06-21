"""KSO Sidecar Production Daemon Loop Core.

Long-running sidecar process:
  period sync manifest/media from gateway →
  periodically scan pending completed PoP →
  build eligible payload → send to backend →
  mark sent only after confirmed accept →
  write safe health/status file →
  graceful stop.

NO systemd. NO backend/player changes. NO migrations.
NO real HTTP in tests. Injectable gateway/http clients.
"""

import json as _json
import os as _os
import tempfile as _tempfile
import time as _time
from dataclasses import dataclass, field
from datetime import datetime as _dt, timezone as _tz
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, cast as _cast

from kso_sidecar_agent.kso_manifest_media_sync import (
    sync_kso_manifest_and_media,
    KsoManifestMediaSyncResult,
    KsoGatewayClient,
    STATUS_OK as SYNC_OK,
    STATUS_NOT_MODIFIED as SYNC_NOT_MODIFIED,
    STATUS_NO_MANIFEST as SYNC_NO_MANIFEST,
    STATUS_ERROR as SYNC_ERROR,
    REASON_SYNCED,
    REASON_NOT_MODIFIED,
    REASON_NO_MANIFEST,
)
from kso_sidecar_agent.pop_scoped_send import (
    run_pop_scoped_send,
    PopScopedSendResult,
    STATUS_OK as SCOPED_OK,
    STATUS_WARNING as SCOPED_WARNING,
    STATUS_ERROR as SCOPED_ERROR,
    REASON_SEND_OK,
    REASON_NO_ELIGIBLE_EVENTS_SCOPED,
    REASON_LOCK_UNAVAILABLE_SCOPED,
    REASON_SEND_FAILED,
)
from kso_sidecar_agent.pop_rotation_apply import (
    apply_pop_rotation_local,
    PopRotationApplyResult,
    STATUS_OK as ROT_OK,
    REASON_APPLIED,
    REASON_PENDING_SHOULD_REMAIN,
    REASON_NO_PENDING_FILE as ROT_NO_PENDING,
    DEFAULT_MAX_LINES,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

DAEMON_STATUS_RUNNING = "running"
DAEMON_STATUS_STOPPING = "stopping"
DAEMON_STATUS_ERROR = "error"
DAEMON_STATUS_STOPPED = "stopped"

ALLOWED_DAEMON_STATUSES = frozenset({
    DAEMON_STATUS_RUNNING,
    DAEMON_STATUS_STOPPING,
    DAEMON_STATUS_ERROR,
    DAEMON_STATUS_STOPPED,
})

# ── Safe reasons ─────────────────────────────────────────────────────

REASON_OK = "ok"
REASON_DAEMON_STOPPED = "daemon_stopped"
REASON_MAX_CYCLES = "max_cycles_reached"
REASON_STOP_CHECK = "stop_check_triggered"
REASON_MAX_CONSECUTIVE_ERRORS = "max_consecutive_errors_exceeded"
REASON_EMPTY_RUN = "empty_run"
REASON_INVALID_ARGS = "invalid_args"

ALLOWED_FINAL_REASONS = frozenset({
    REASON_OK,
    REASON_DAEMON_STOPPED,
    REASON_MAX_CYCLES,
    REASON_STOP_CHECK,
    REASON_MAX_CONSECUTIVE_ERRORS,
    REASON_EMPTY_RUN,
    REASON_INVALID_ARGS,
})

# ── Cycle sub-statuses ───────────────────────────────────────────────

CYCLE_STATUS_OK = "ok"
CYCLE_STATUS_SYNC_ERROR = "sync_error"
CYCLE_STATUS_POP_SEND_ERROR = "pop_send_error"
CYCLE_STATUS_POP_ROTATE_ERROR = "pop_rotate_error"
CYCLE_STATUS_NO_POP = "no_pop"
CYCLE_STATUS_SENT = "sent"

ALLOWED_CYCLE_STATUSES = frozenset({
    CYCLE_STATUS_OK,
    CYCLE_STATUS_SYNC_ERROR,
    CYCLE_STATUS_POP_SEND_ERROR,
    CYCLE_STATUS_POP_ROTATE_ERROR,
    CYCLE_STATUS_NO_POP,
    CYCLE_STATUS_SENT,
})

# ── Forbidden in health ──────────────────────────────────────────────

_FORBIDDEN_IN_HEALTH = frozenset({
    "path", "file_path", "local_path", "filesystem_path",
    "filename", "media_path", "media_ref", "mediaRef",
    "manifest_item_id", "manifest_version_id", "manifest_hash",
    "campaign_id", "creative_id", "rendition_id",
    "schedule_item_id", "batch_id", "booking_id",
    "device_event_id", "token", "secret", "password",
    "credential", "authorization", "cookie", "api_key",
    "private_key", "public_key", "minio", "presigned",
    "stacktrace", "sha256", "raw", "body",
    "backend_url", "backend_base_url", "device_code",
})


# ══════════════════════════════════════════════════════════════════════
# Health file
# ══════════════════════════════════════════════════════════════════════

def _validate_health_dict(data: dict) -> None:
    """Validate health dict has no forbidden keys/values."""
    def _check_value(v: Any, path: str = "") -> None:
        if isinstance(v, str):
            lower = v.lower()
            for fb in _FORBIDDEN_IN_HEALTH:
                if fb in lower:
                    raise ValueError(
                        f"Health field '{path}' contains forbidden substring '{fb}'"
                    )
        elif isinstance(v, dict):
            for k, sv in v.items():
                _check_value(sv, f"{path}.{k}" if path else k)
        elif isinstance(v, list):
            for i, sv in enumerate(v):
                _check_value(sv, f"{path}[{i}]")

    for key, value in data.items():
        if isinstance(key, str):
            lower = key.lower()
            for fb in _FORBIDDEN_IN_HEALTH:
                if fb in lower:
                    raise ValueError(f"Forbidden health key '{key}'")
        _check_value(value, str(key))


def _write_health_file_atomic(health_file: str, data: dict) -> None:
    """Write health JSON atomically. Raises on validation failure."""
    _validate_health_dict(data)

    target = Path(health_file).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = _tempfile.mkstemp(
        dir=str(target.parent),
        prefix="." + target.name + ".",
        suffix=".tmp",
    )
    try:
        _os.write(fd, _json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
        _os.fsync(fd)
    finally:
        _os.close(fd)

    _os.replace(tmp_path, str(target))


def _build_health_data(
    status: str,
    cycles_completed: int,
    last_sync_status: str,
    last_pop_send_status: str,
    last_pop_rotate_status: str,
    sync_ok_count: int,
    sync_error_count: int,
    pop_sent_count: int,
    pop_error_count: int,
    pending_preserved_count: int,
    manifest_written: bool,
    media_written_count: int,
    pop_payload_events: int,
    pop_sent_records: int,
    pending_preserved_this_cycle: bool,
    error_count: int,
    last_reason: str,
    daemon_status: str,
) -> dict:
    """Build a safe health dict."""
    return {
        "status": status,
        "daemon_status": daemon_status,
        "cycles_completed": cycles_completed,
        "last_sync_status": last_sync_status,
        "last_pop_send_status": last_pop_send_status,
        "last_pop_rotate_status": last_pop_rotate_status,
        "sync_ok_count": sync_ok_count,
        "sync_error_count": sync_error_count,
        "pop_sent_count": pop_sent_count,
        "pop_error_count": pop_error_count,
        "pending_preserved_count": pending_preserved_count,
        "manifest_written": manifest_written,
        "media_written_count": media_written_count,
        "pop_payload_events": pop_payload_events,
        "pop_sent_records": pop_sent_records,
        "pending_preserved_this_cycle": pending_preserved_this_cycle,
        "error_count": error_count,
        "last_reason": last_reason,
    }


# ══════════════════════════════════════════════════════════════════════
# Auth provider contract
# ══════════════════════════════════════════════════════════════════════

class AuthProvider(Protocol):
    """Injectable auth token provider."""
    def __call__(self) -> Optional[str]:
        """Return access token string or None on failure."""
        ...


# ══════════════════════════════════════════════════════════════════════
# Result
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoSidecarDaemonResult:
    """Safe result of sidecar daemon loop.

    Never contains: paths, filenames, raw manifest, raw JSON,
    IDs, hash, token, secret, backend URL, stacktrace.
    """

    status: str = DAEMON_STATUS_STOPPED
    cycles_completed: int = 0
    sync_ok_count: int = 0
    sync_error_count: int = 0
    pop_sent_count: int = 0
    pop_error_count: int = 0
    pending_preserved_count: int = 0
    error_count: int = 0
    health_written: bool = False
    reason: str = REASON_EMPTY_RUN

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_DAEMON_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'")
        if self.reason not in ALLOWED_FINAL_REASONS:
            raise ValueError(f"Invalid reason '{self.reason}'")

    def __repr__(self) -> str:
        return (
            f"KsoSidecarDaemonResult("
            f"status={self.status!r}, "
            f"cycles_completed={self.cycles_completed}, "
            f"sync_ok_count={self.sync_ok_count}, "
            f"sync_error_count={self.sync_error_count}, "
            f"pop_sent_count={self.pop_sent_count}, "
            f"pop_error_count={self.pop_error_count}, "
            f"pending_preserved_count={self.pending_preserved_count}, "
            f"error_count={self.error_count}, "
            f"health_written={self.health_written}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_kso_sidecar_daemon(
    root: str,
    gateway_client: KsoGatewayClient,
    http_client: Any,  # SafeHttpClient-like
    auth_provider: Optional[AuthProvider] = None,
    max_cycles: Optional[int] = None,
    sync_interval_seconds: int = 30,
    pop_interval_seconds: int = 10,
    stop_check: Optional[Callable[[], bool]] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    health_file: Optional[str] = None,
    max_consecutive_errors: int = 3,
) -> KsoSidecarDaemonResult:
    """Run sidecar daemon loop.

    Each cycle:
      1. Check stop_check()
      2. Sync manifest + media from gateway
      3. Pick up completed PoP → build payload → send to backend
      4. If backend confirmed accept → rotate pending to sent
      5. Write safe health file (if health_file provided)
      6. Wait (sleep_fn)

    Pending NEVER deleted/moved without confirmed backend accept.

    Args:
        root: Agent root path.
        gateway_client: Injectable KSO gateway client.
        http_client: Injectable HTTP client with post_json(path, payload, headers).
        auth_provider: Optional callable → access_token string.
        max_cycles: Max cycles (None = run forever until stopped).
        sync_interval_seconds: Unused placeholder (future granular scheduling).
        pop_interval_seconds: Unused placeholder (future granular scheduling).
        stop_check: Callable → True if daemon should stop.
        sleep_fn: Callable(seconds) for waiting between cycles.
        health_file: Optional path for atomic health JSON.
        max_consecutive_errors: Stop after N consecutive errors (default 3).

    Returns:
        KsoSidecarDaemonResult — safe, never raises.
    """
    # ── Validate args ──────────────────────────────────────────────
    if not isinstance(max_consecutive_errors, int) or max_consecutive_errors < 1:
        return KsoSidecarDaemonResult(
            status=DAEMON_STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        _root = Path(root)
    except Exception:
        return KsoSidecarDaemonResult(
            status=DAEMON_STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    if gateway_client is None or http_client is None:
        return KsoSidecarDaemonResult(
            status=DAEMON_STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    _sleep = sleep_fn if sleep_fn is not None else _time.sleep
    _stop = stop_check if stop_check is not None else (lambda: False)

    # ── State ──────────────────────────────────────────────────────
    completed = 0
    sync_ok = 0
    sync_err = 0
    pop_ok = 0
    pop_err = 0
    pending_preserved = 0
    consecutive_errors = 0
    daemon_status = DAEMON_STATUS_RUNNING

    last_sync_status = "initial"
    last_pop_send_status = "initial"
    last_pop_rotate_status = "initial"
    manifest_written_flag = False
    media_written = 0
    pop_payload_events = 0
    pop_sent_records = 0
    pending_preserved_this = False

    reason = REASON_OK

    # ── Main loop ──────────────────────────────────────────────────
    while True:
        # 1. Stop check
        if _stop():
            reason = REASON_STOP_CHECK
            daemon_status = DAEMON_STATUS_STOPPING
            break

        # 2. Max cycles check (before cycle execution)
        if max_cycles is not None and completed >= max_cycles:
            reason = REASON_MAX_CYCLES
            daemon_status = DAEMON_STATUS_STOPPING
            break

        cycle_error = False
        pending_preserved_this = False

        # ── Sync manifest + media ──────────────────────────────
        try:
            sync_result = sync_kso_manifest_and_media(_root, gateway_client)
            if sync_result.status in (SYNC_OK, SYNC_NOT_MODIFIED, SYNC_NO_MANIFEST):
                last_sync_status = sync_result.status
                sync_ok += 1
                manifest_written_flag = sync_result.manifest_written
                media_written = sync_result.media_written_count
            else:
                last_sync_status = CYCLE_STATUS_SYNC_ERROR
                sync_err += 1
                cycle_error = True
        except Exception:
            last_sync_status = CYCLE_STATUS_SYNC_ERROR
            sync_err += 1
            cycle_error = True

        # ── PoP send: pickup → payload → send → rotate ─────────
        pop_attempted = False
        try:
            scoped_result = run_pop_scoped_send(
                _root,
                http_client=http_client,
                auth_provider=auth_provider,
                max_lines=DEFAULT_MAX_LINES,
            )

            if scoped_result.status == SCOPED_ERROR:
                last_pop_send_status = CYCLE_STATUS_POP_SEND_ERROR
                pop_err += 1
                cycle_error = True
                pending_preserved_this = True
                pop_attempted = True
            elif scoped_result.send_success and scoped_result._send_run_result is not None:
                # Backend confirmed accept → rotate pending to sent
                try:
                    rot_result = apply_pop_rotation_local(
                        _root,
                        send_run_result=scoped_result._send_run_result,
                        sent_scope=scoped_result._sent_scope,
                        max_lines=DEFAULT_MAX_LINES,
                    )
                    if rot_result.status == ROT_OK:
                        last_pop_rotate_status = REASON_APPLIED
                        pop_ok += 1
                        pop_payload_events = scoped_result.payload_events
                        pop_sent_records = rot_result.sent_records
                    elif rot_result.reason in (REASON_PENDING_SHOULD_REMAIN, ROT_NO_PENDING):
                        last_pop_rotate_status = rot_result.reason
                        pending_preserved_this = True
                        pending_preserved += 1
                    else:
                        last_pop_rotate_status = CYCLE_STATUS_POP_ROTATE_ERROR
                        pop_err += 1
                        cycle_error = True
                except Exception:
                    last_pop_rotate_status = CYCLE_STATUS_POP_ROTATE_ERROR
                    pop_err += 1
                    cycle_error = True
            elif scoped_result.reason == REASON_NO_ELIGIBLE_EVENTS_SCOPED:
                last_pop_send_status = CYCLE_STATUS_NO_POP
                last_pop_rotate_status = CYCLE_STATUS_NO_POP
            elif scoped_result.reason == REASON_LOCK_UNAVAILABLE_SCOPED:
                last_pop_send_status = CYCLE_STATUS_POP_SEND_ERROR
                pop_err += 1
                cycle_error = True
            else:
                # Send attempted but pending should remain
                last_pop_send_status = CYCLE_STATUS_POP_SEND_ERROR
                pop_err += 1
                cycle_error = True
                pending_preserved_this = True
        except Exception:
            last_pop_send_status = CYCLE_STATUS_POP_SEND_ERROR
            pop_err += 1
            cycle_error = True

        # ── Track pending preserved ────────────────────────────
        if pending_preserved_this:
            pending_preserved += 1

        # ── Error tracking ─────────────────────────────────────
        if cycle_error:
            consecutive_errors += 1
        else:
            consecutive_errors = 0

        completed += 1

        # ── Health file ────────────────────────────────────────
        if health_file is not None:
            try:
                health_data = _build_health_data(
                    status="ok" if not cycle_error else "error",
                    cycles_completed=completed,
                    last_sync_status=last_sync_status,
                    last_pop_send_status=last_pop_send_status,
                    last_pop_rotate_status=last_pop_rotate_status,
                    sync_ok_count=sync_ok,
                    sync_error_count=sync_err,
                    pop_sent_count=pop_ok,
                    pop_error_count=pop_err,
                    pending_preserved_count=pending_preserved,
                    manifest_written=manifest_written_flag,
                    media_written_count=media_written,
                    pop_payload_events=pop_payload_events,
                    pop_sent_records=pop_sent_records,
                    pending_preserved_this_cycle=pending_preserved_this,
                    error_count=consecutive_errors,
                    last_reason=reason,
                    daemon_status=daemon_status,
                )
                _write_health_file_atomic(health_file, health_data)
            except Exception:
                pass  # Health file is best-effort

        # ── Consecutive error limit ────────────────────────────
        if consecutive_errors >= max_consecutive_errors:
            reason = REASON_MAX_CONSECUTIVE_ERRORS
            daemon_status = DAEMON_STATUS_ERROR
            break

        # ── Wait ────────────────────────────────────────────────
        try:
            _sleep(sync_interval_seconds)
        except Exception:
            # sleep interrupted — let stop_check handle next cycle
            pass

    # ── Final health file ──────────────────────────────────────────
    if reason == REASON_MAX_CONSECUTIVE_ERRORS:
        daemon_status = DAEMON_STATUS_ERROR
    else:
        daemon_status = DAEMON_STATUS_STOPPED

    if health_file is not None:
        try:
            health_data = _build_health_data(
                status="ok",
                cycles_completed=completed,
                last_sync_status=last_sync_status,
                last_pop_send_status=last_pop_send_status,
                last_pop_rotate_status=last_pop_rotate_status,
                sync_ok_count=sync_ok,
                sync_error_count=sync_err,
                pop_sent_count=pop_ok,
                pop_error_count=pop_err,
                pending_preserved_count=pending_preserved,
                manifest_written=manifest_written_flag,
                media_written_count=media_written,
                pop_payload_events=pop_payload_events,
                pop_sent_records=pop_sent_records,
                pending_preserved_this_cycle=False,
                error_count=consecutive_errors,
                last_reason=reason,
                daemon_status=daemon_status,
            )
            _write_health_file_atomic(health_file, health_data)
        except Exception:
            pass

    return KsoSidecarDaemonResult(
        status=daemon_status,
        cycles_completed=completed,
        sync_ok_count=sync_ok,
        sync_error_count=sync_err,
        pop_sent_count=pop_ok,
        pop_error_count=pop_err,
        pending_preserved_count=pending_preserved,
        error_count=consecutive_errors,
        health_written=health_file is not None and Path(health_file).exists(),
        reason=reason,
    )


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_kso_sidecar_daemon_result(result: KsoSidecarDaemonResult) -> str:
    """Return a safe aggregated string.

    Never prints: paths, filenames, raw manifest, raw JSON,
    IDs, hash, token, secret, backend URL, stacktrace.
    """
    lines = [
        f"status:                  {result.status}",
        f"cycles_completed:         {result.cycles_completed}",
        f"sync_ok_count:            {result.sync_ok_count}",
        f"sync_error_count:         {result.sync_error_count}",
        f"pop_sent_count:           {result.pop_sent_count}",
        f"pop_error_count:          {result.pop_error_count}",
        f"pending_preserved_count:  {result.pending_preserved_count}",
        f"error_count:              {result.error_count}",
        f"health_written:           {str(result.health_written).lower()}",
        f"reason:                   {result.reason}",
    ]

    output = "\n".join(lines)

    # Safety scan
    lower = output.lower()
    for fb in _FORBIDDEN_IN_HEALTH:
        if fb in lower:
            raise ValueError(
                f"Safe output contains forbidden substring '{fb}'"
            )

    return output
