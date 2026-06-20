"""KSO Player Local Shell Snapshot Core — safe JSON snapshot for HTML shell.

Converts a shell_command into a safe serializable snapshot for the future
Chromium kiosk HTML shell (window.KsoPlayerShell.applySnapshot).

Pipeline: runtime_gate → runtime_decision → render_plan → shell_command → shell_snapshot

The snapshot carries ONLY safe fields: schemaVersion, mode, method, payload.
NO media src, NO paths, NO filenames, NO manifest IDs, NO hashes, NO timestamps.

NO Chromium, NO HTTP, NO PoP write, NO backend.
"""

import json as _json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from kso_player.shell_command import (
    build_kso_shell_command,
    KsoShellCommandResult,
    SHELL_MODE_HOLD,
    SHELL_MODE_RENDER,
    COMMAND_HOLD,
    COMMAND_SET_RENDER_PLAN,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    REASON_READY_FOR_SHELL,
    REASON_RENDER_PLAN_HOLD,
    REASON_INVALID_ARGS,
    REASON_INTERNAL_ERROR,
    FORBIDDEN_SUBSTRINGS,
)
from kso_player.render_plan import (
    MEDIA_IMAGE, MEDIA_VIDEO, MEDIA_UNKNOWN,
    DURATION_SHORT, DURATION_MEDIUM, DURATION_LONG, DURATION_UNKNOWN,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

SNAPSHOT_SCHEMA_VERSION = 1

SNAPSHOT_MODE_HOLD = "hold"
SNAPSHOT_MODE_RENDER = "render"

SNAPSHOT_METHOD_SET_HOLD = "setHold"
SNAPSHOT_METHOD_SET_RENDER_PLAN = "setRenderPlan"

SIZE_BUCKET_SMALL = "small"    # < 256 bytes
SIZE_BUCKET_MEDIUM = "medium"  # 256–1024 bytes
SIZE_BUCKET_LARGE = "large"    # > 1024 bytes
SIZE_BUCKET_UNKNOWN = "unknown"

# ── Safe payload keys ────────────────────────────────────────────────

SAFE_PAYLOAD_KEYS = frozenset({"mediaType", "durationBucket", "reason"})
SAFE_TOP_KEYS = frozenset({"schemaVersion", "mode", "method", "payload"})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoShellSnapshotResult:
    """Safe shell snapshot for the HTML shell (window.KsoPlayerShell API).

    Carry only safe fields: snapshot_mode, shell_method, media_type,
    duration_bucket. The serialized JSON contains only schemaVersion,
    mode, method, payload.

    NEVER: paths, filenames, media src, manifest IDs, hashes, timestamps.
    """

    status: str = STATUS_ERROR
    snapshot_mode: str = SNAPSHOT_MODE_HOLD
    shell_method: str = SNAPSHOT_METHOD_SET_HOLD
    reason: str = REASON_INVALID_ARGS
    media_type: str = MEDIA_UNKNOWN
    duration_bucket: str = DURATION_UNKNOWN
    pop_event_should_be_written: bool = False
    serialized_size_bucket: str = SIZE_BUCKET_UNKNOWN

    # Internal fields — NEVER exposed in safe output
    _serialized: str = ""

    def __repr__(self) -> str:
        return (
            f"KsoShellSnapshotResult("
            f"status={self.status!r}, "
            f"snapshot_mode={self.snapshot_mode!r}, "
            f"shell_method={self.shell_method!r}, "
            f"reason={self.reason!r}, "
            f"media_type={self.media_type!r}, "
            f"duration_bucket={self.duration_bucket!r}, "
            f"pop_event_should_be_written={self.pop_event_should_be_written}, "
            f"serialized_size_bucket={self.serialized_size_bucket!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _classify_size_bucket(json_str: str) -> str:
    """Classify serialized snapshot size."""
    size = len(json_str.encode("utf-8"))
    if size < 256:
        return SIZE_BUCKET_SMALL
    if size <= 1024:
        return SIZE_BUCKET_MEDIUM
    return SIZE_BUCKET_LARGE


def _safe_serialized_contains_forbidden(s: str) -> bool:
    """Check if serialized snapshot contains any forbidden substring."""
    lower = s.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def build_kso_shell_snapshot(
    root,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
) -> KsoShellSnapshotResult:
    """Build a safe shell snapshot from shell command.

    Pipeline: shell_command → shell_snapshot.

    If command == "hold":
        snapshot_mode=hold, shell_method=setHold,
        payload={"reason":"hold"}

    If command == "setRenderPlan":
        snapshot_mode=render, shell_method=setRenderPlan,
        payload={"mediaType":"image|video","durationBucket":"short|medium|long|unknown"}

    IMPORTANT: Snapshot has NO media src. Real media source will be
    a separate step after a separate security design.

    Args:
        root: Agent root path (str or Path).
        stale_seconds: Max state age before stale (default 30s).
        now: Optional datetime for test time injection.

    Returns:
        KsoShellSnapshotResult — safe aggregate, never raises.
    """
    # ── Build shell command ──────────────────────────────────────────
    try:
        cmd = build_kso_shell_command(root, stale_seconds, now)
    except Exception:
        return KsoShellSnapshotResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
        )

    # ── Hold path ────────────────────────────────────────────────────
    if cmd.command == COMMAND_HOLD:
        snapshot = KsoShellSnapshotResult(
            status=cmd.status,
            snapshot_mode=SNAPSHOT_MODE_HOLD,
            shell_method=SNAPSHOT_METHOD_SET_HOLD,
            reason=cmd.reason,
            pop_event_should_be_written=cmd.pop_event_should_be_written,
        )
    # ── Render path ──────────────────────────────────────────────────
    elif cmd.command == COMMAND_SET_RENDER_PLAN:
        snapshot = KsoShellSnapshotResult(
            status=cmd.status,
            snapshot_mode=SNAPSHOT_MODE_RENDER,
            shell_method=SNAPSHOT_METHOD_SET_RENDER_PLAN,
            reason=cmd.reason,
            media_type=cmd.media_type,
            duration_bucket=cmd.duration_bucket,
            pop_event_should_be_written=cmd.pop_event_should_be_written,
        )
    else:
        # Unexpected command — hold
        return KsoShellSnapshotResult(
            status=STATUS_ERROR,
            reason=cmd.reason,
        )

    # ── Serialize and classify ───────────────────────────────────────
    try:
        serialized = serialize_kso_shell_snapshot(snapshot)
        snapshot._serialized = serialized
        snapshot.serialized_size_bucket = _classify_size_bucket(serialized)
    except Exception:
        snapshot._serialized = ""
        snapshot.serialized_size_bucket = SIZE_BUCKET_UNKNOWN

    return snapshot


def serialize_kso_shell_snapshot(result: KsoShellSnapshotResult) -> str:
    """Serialize a KsoShellSnapshotResult to a safe JSON string.

    Contains ONLY: schemaVersion, mode, method, payload.
    payload keys only: mediaType, durationBucket (render) or reason (hold).

    NEVER: paths, filenames, IDs, hashes, timestamps, secrets.

    Returns:
        JSON string with only safe fields.
    """
    if result.snapshot_mode == SNAPSHOT_MODE_RENDER:
        payload = {
            "mediaType": result.media_type,
            "durationBucket": result.duration_bucket,
        }
    else:
        payload = {"reason": "hold"}

    obj = {
        "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
        "mode": result.snapshot_mode,
        "method": result.shell_method,
        "payload": payload,
    }

    serialized = _json.dumps(obj, sort_keys=True, separators=(",", ":"))

    # Safety check: serialized must never contain forbidden substrings
    if _safe_serialized_contains_forbidden(serialized):
        # Fallback: return minimal safe hold
        return _json.dumps(
            {
                "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
                "mode": SNAPSHOT_MODE_HOLD,
                "method": SNAPSHOT_METHOD_SET_HOLD,
                "payload": {"reason": "hold"},
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    return serialized


def format_kso_shell_snapshot_result(result: KsoShellSnapshotResult) -> str:
    """Format a KsoShellSnapshotResult as a safe human-readable string.

    Never contains paths, filenames, IDs, hashes, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"snapshot_mode: {result.snapshot_mode}",
        f"shell_method: {result.shell_method}",
        f"reason: {result.reason}",
        f"media_type: {result.media_type}",
        f"duration_bucket: {result.duration_bucket}",
        f"pop_event_should_be_written: "
        f"{str(result.pop_event_should_be_written).lower()}",
        f"serialized_size_bucket: {result.serialized_size_bucket}",
    ]
    return "\n".join(lines)
