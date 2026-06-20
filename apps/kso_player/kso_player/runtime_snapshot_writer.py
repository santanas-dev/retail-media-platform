"""KSO Player Runtime Snapshot Writer — atomic bootstrap_snapshot.js output.

Writes the current shell snapshot to {runtime_shell_dir}/bootstrap_snapshot.js
using atomic writes (tmp → flush → fsync → rename → fsync dir).

Pipeline: state/kso_state.json → runtime_gate → runtime_decision →
  render_plan → shell_command → shell_snapshot → bootstrap_snapshot.js

Writer targets ONLY the runtime shell copy — NEVER the immutable /opt source.
NO external processes, NO service managers, NO backend, NO PoP write, NO state write.
"""

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from kso_player.shell_snapshot import (
    build_kso_shell_snapshot,
    serialize_kso_shell_snapshot,
    KsoShellSnapshotResult,
    SNAPSHOT_MODE_HOLD,
    SNAPSHOT_MODE_RENDER,
    SNAPSHOT_METHOD_SET_HOLD,
    SNAPSHOT_METHOD_SET_RENDER_PLAN,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    FORBIDDEN_SUBSTRINGS,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

SNAPSHOT_FILE = "bootstrap_snapshot.js"

REASON_WRITTEN = "written"
REASON_SNAPSHOT_HOLD = "snapshot_hold"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"
REASON_WRITE_FAILED = "write_failed"
REASON_RUNTIME_DIR_ERROR = "runtime_dir_error"

BYTES_SMALL = "small"      # < 256
BYTES_MEDIUM = "medium"    # 256–1024
BYTES_LARGE = "large"      # > 1024
BYTES_UNKNOWN = "unknown"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoRuntimeSnapshotWriteResult:
    """Safe result of writing bootstrap_snapshot.js.

    NEVER contains paths, filenames, mediaRef, raw snapshot JSON,
    exception text, or forbidden substrings.
    """

    status: str = STATUS_ERROR
    written: bool = False
    snapshot_mode: str = SNAPSHOT_MODE_HOLD
    shell_method: str = SNAPSHOT_METHOD_SET_HOLD
    reason: str = REASON_INVALID_ARGS
    bytes_bucket: str = BYTES_UNKNOWN

    def __repr__(self) -> str:
        return (
            f"KsoRuntimeSnapshotWriteResult("
            f"status={self.status!r}, "
            f"written={self.written}, "
            f"snapshot_mode={self.snapshot_mode!r}, "
            f"shell_method={self.shell_method!r}, "
            f"reason={self.reason!r}, "
            f"bytes_bucket={self.bytes_bucket!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _build_js_content(snapshot_json: str) -> str:
    """Build safe bootstrap_snapshot.js content from serialized snapshot.

    Returns a JS string that sets window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT.
    NEVER includes paths, IDs, hashes, or raw data beyond the safe snapshot.
    """
    return (
        '"use strict";\n'
        f"window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT = {snapshot_json};\n"
    )


def _classify_bytes(data: str) -> str:
    size = len(data.encode("utf-8"))
    if size < 256:
        return BYTES_SMALL
    if size <= 1024:
        return BYTES_MEDIUM
    return BYTES_LARGE


def _atomic_write(dst_path: Path, content: str) -> bool:
    """Write content to dst atomically (tmp → rename)."""
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(dst_path.parent),
            prefix="." + dst_path.name + ".",
            suffix=".tmp",
        )
        try:
            data = content.encode("utf-8")
            os.write(fd, data)
            os.fsync(fd)
        except Exception:
            os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return False
        finally:
            os.close(fd)

        os.replace(tmp_path, str(dst_path))

        try:
            fd_dir = os.open(str(dst_path.parent), os.O_RDONLY)
            os.fsync(fd_dir)
            os.close(fd_dir)
        except OSError:
            pass

        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def write_kso_runtime_bootstrap_snapshot(
    root,
    runtime_shell_dir,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
) -> KsoRuntimeSnapshotWriteResult:
    """Write bootstrap_snapshot.js to the runtime shell directory.

    Builds the current shell snapshot from local state/manifest/media,
    serializes it to safe JSON, wraps it in JS, and atomically writes
    to {runtime_shell_dir}/bootstrap_snapshot.js.

    Writer targets ONLY the runtime shell copy.
    NEVER writes to /opt, NEVER writes PoP, NEVER writes state.

    Args:
        root: Agent root path (str or Path) — has state/, manifest/, media/.
        runtime_shell_dir: Path to runtime shell copy directory.
        stale_seconds: Max state age (default 30s).
        now: Optional datetime for test time injection.

    Returns:
        KsoRuntimeSnapshotWriteResult — safe aggregate, never raises.
    """
    # ── Validate args ────────────────────────────────────────────
    if stale_seconds <= 0:
        return KsoRuntimeSnapshotWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoRuntimeSnapshotWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        runtime_dir = Path(runtime_shell_dir)
    except (TypeError, ValueError):
        return KsoRuntimeSnapshotWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Build snapshot ───────────────────────────────────────────
    try:
        snapshot = build_kso_shell_snapshot(root, stale_seconds, now)
    except Exception:
        return KsoRuntimeSnapshotWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
        )

    # ── Serialize snapshot to safe JSON ──────────────────────────
    try:
        snapshot_json = serialize_kso_shell_snapshot(snapshot)
    except Exception:
        return KsoRuntimeSnapshotWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
        )

    # ── Build JS content ─────────────────────────────────────────
    try:
        js_content = _build_js_content(snapshot_json)
    except Exception:
        return KsoRuntimeSnapshotWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
        )

    # ── Ensure runtime dir exists ────────────────────────────────
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return KsoRuntimeSnapshotWriteResult(
            status=STATUS_ERROR,
            reason=REASON_RUNTIME_DIR_ERROR,
            snapshot_mode=snapshot.snapshot_mode,
            shell_method=snapshot.shell_method,
        )

    # ── Atomic write ─────────────────────────────────────────────
    dst_path = runtime_dir / SNAPSHOT_FILE
    try:
        if not _atomic_write(dst_path, js_content):
            return KsoRuntimeSnapshotWriteResult(
                status=STATUS_ERROR,
                reason=REASON_WRITE_FAILED,
                snapshot_mode=snapshot.snapshot_mode,
                shell_method=snapshot.shell_method,
            )
    except Exception:
        return KsoRuntimeSnapshotWriteResult(
            status=STATUS_ERROR,
            reason=REASON_WRITE_FAILED,
            snapshot_mode=snapshot.snapshot_mode,
            shell_method=snapshot.shell_method,
        )

    bytes_bucket = _classify_bytes(js_content)

    return KsoRuntimeSnapshotWriteResult(
        status=STATUS_OK if snapshot.snapshot_mode == SNAPSHOT_MODE_RENDER else STATUS_OK,
        written=True,
        snapshot_mode=snapshot.snapshot_mode,
        shell_method=snapshot.shell_method,
        reason=REASON_WRITTEN,
        bytes_bucket=bytes_bucket,
    )


def format_kso_runtime_snapshot_write_result(
    result: KsoRuntimeSnapshotWriteResult,
) -> str:
    """Format result as a safe human-readable string.

    Never contains paths, filenames, mediaRef, raw JSON, exception text,
    or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"written: {str(result.written).lower()}",
        f"snapshot_mode: {result.snapshot_mode}",
        f"shell_method: {result.shell_method}",
        f"reason: {result.reason}",
        f"bytes_bucket: {result.bytes_bucket}",
    ]
    return "\n".join(lines)
