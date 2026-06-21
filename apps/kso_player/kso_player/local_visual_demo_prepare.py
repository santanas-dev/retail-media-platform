"""KSO Player Local Visual Demo Prepare Core — full vertical demo prepare.

Pipeline:
  state/kso_state.json → runtime_gate → runtime_decision →
    render_plan → shell_command → shell_snapshot → bootstrap_snapshot.js

Demo prepare adds:
  source shell → atomic copy → runtime shell
  media alias → safe symlink → runtime shell (render only)
  snapshot → atomic write → bootstrap_snapshot.js

After prepare, runtime shell is ready for manual Chromium launch.
NO Chromium, NO systemd, NO backend, NO PoP write, NO state write.
"""

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from kso_player.runtime_shell_workspace import (
    prepare_kso_runtime_shell_workspace,
    STATUS_OK as WS_STATUS_OK,
    STATUS_ERROR as WS_STATUS_ERROR,
)
from kso_player.shell_snapshot import (
    build_kso_shell_snapshot,
    SNAPSHOT_MODE_HOLD,
    SNAPSHOT_MODE_RENDER,
    SNAPSHOT_METHOD_SET_HOLD,
    SNAPSHOT_METHOD_SET_RENDER_PLAN,
    STATUS_OK as SS_STATUS_OK,
    STATUS_WARNING as SS_STATUS_WARNING,
    STATUS_ERROR as SS_STATUS_ERROR,
    FORBIDDEN_SUBSTRINGS,
)
from kso_player.render_plan import (
    build_kso_render_plan,
    MEDIA_IMAGE, MEDIA_VIDEO, MEDIA_UNKNOWN,
    RENDER_ACTION_RENDER,
)
from kso_player.runtime_snapshot_writer import (
    write_kso_runtime_bootstrap_snapshot,
    SNAPSHOT_MODE_HOLD as SW_HOLD,
    SNAPSHOT_MODE_RENDER as SW_RENDER,
    STATUS_OK as SW_STATUS_OK,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

REASON_PREPARED = "prepared"
REASON_WORKSPACE_FAILED = "workspace_prepare_failed"
REASON_SNAPSHOT_BUILD_FAILED = "snapshot_build_failed"
REASON_MEDIA_ALIAS_FAILED = "media_alias_failed"
REASON_SNAPSHOT_WRITE_FAILED = "snapshot_write_failed"
REASON_INVALID_ARGS = "invalid_args"

MEDIA_CURRENT_ALIAS_DIR = "media/current"

# Hold snapshot JS — safe default when render aliases fail
_HOLD_SNAPSHOT_JS = (
    '"use strict";\n'
    'window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT = '
    '{"schemaVersion":1,"mode":"hold","method":"setHold",'
    '"payload":{"reason":"hold"}};\n'
)


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoLocalVisualDemoPrepareResult:
    """Safe result of local visual demo preparation.

    NEVER contains absolute paths, filenames, mediaRef values, IDs,
    raw JSON, exception text, or forbidden substrings.
    """

    status: str = STATUS_ERROR
    prepared: bool = False
    workspace_ready: bool = False
    snapshot_written: bool = False
    snapshot_mode: str = SNAPSHOT_MODE_HOLD
    media_alias_ready: bool = False
    reason: str = REASON_INVALID_ARGS

    def __repr__(self) -> str:
        return (
            f"KsoLocalVisualDemoPrepareResult("
            f"status={self.status!r}, "
            f"prepared={self.prepared}, "
            f"workspace_ready={self.workspace_ready}, "
            f"snapshot_written={self.snapshot_written}, "
            f"snapshot_mode={self.snapshot_mode!r}, "
            f"media_alias_ready={self.media_alias_ready}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _validate_media_root(media_path: Path, root: Path) -> bool:
    """Check that media_path is safely inside root's media/ directory."""
    try:
        resolved = media_path.resolve()
        root_resolved = (root / "media").resolve()
        return resolved.is_relative_to(root_resolved)
    except (OSError, ValueError):
        return False


def _validate_filename_safe(filename: str) -> bool:
    """Reject unsafe filenames with path traversal or control chars."""
    if not isinstance(filename, str) or not filename.strip():
        return False
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    if "\x00" in filename:
        return False
    return True


def _create_safe_symlink(src: Path, dst_dir: Path, alias_name: str) -> bool:
    """Create a safe symlink alias in dst_dir.

    Symlink dst_dir/alias_name → src.
    src must already be validated as inside the media root.
    Never writes outside dst_dir.
    """
    try:
        # Validate alias name — only safe chars
        if not isinstance(alias_name, str):
            return False
        if ".." in alias_name or "/" in alias_name or "\\" in alias_name:
            return False
        if not alias_name.strip():
            return False

        dst = dst_dir / alias_name
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing if any
        if dst.is_symlink() or dst.exists():
            try:
                dst.unlink()
            except OSError:
                return False

        dst.symlink_to(src)
        return True
    except (OSError, ValueError):
        return False


def _prepare_media_aliases(
    root: Path,
    runtime_shell_dir: Path,
    stale_seconds: int,
    now: Optional[datetime],
) -> bool:
    """Prepare safe media aliases for render snapshot.

    Reads the current render plan to get selected item filename,
    validates it's inside {root}/media/, then creates a safe symlink:
      {runtime_shell_dir}/media/current/slot-{order:03d} → {root}/media/current/{filename}

    Returns True if the alias was created successfully.
    """
    try:
        render_plan = build_kso_render_plan(root, stale_seconds, now)
    except Exception:
        return False

    if getattr(render_plan, "render_action", "") != RENDER_ACTION_RENDER:
        return False

    selected_item = getattr(render_plan, "_selected_item", None)
    if selected_item is None:
        return False

    filename = getattr(selected_item, "filename", None)
    if not isinstance(filename, str) or not _validate_filename_safe(filename):
        return False

    order = getattr(selected_item, "order", None)
    if not isinstance(order, int) or order < 0:
        return False

    src_media = root / "media" / "current" / str(filename)
    if not _validate_media_root(src_media, root):
        return False

    if not src_media.is_file():
        return False

    alias_name = f"slot-{order:03d}"
    alias_dir = runtime_shell_dir / "media" / "current"

    return _create_safe_symlink(src_media, alias_dir, alias_name)


def _atomic_write_hold_snapshot(dst: Path) -> bool:
    """Atomically write a minimal hold snapshot JS to dst."""
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(dst.parent),
            prefix="." + dst.name + ".",
            suffix=".tmp",
        )
        try:
            data = _HOLD_SNAPSHOT_JS.encode("utf-8")
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

        os.replace(tmp_path, str(dst))

        try:
            fd_dir = os.open(str(dst.parent), os.O_RDONLY)
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

def prepare_kso_local_visual_demo(
    root,
    source_shell_dir,
    runtime_shell_dir,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
) -> KsoLocalVisualDemoPrepareResult:
    """Prepare a local visual demo: workspace + media alias + bootstrap snapshot.

    Full pipeline:
    1. prepare_kso_runtime_shell_workspace(source, runtime) — atomic copy 5 files
    2. build_kso_shell_snapshot(root) — snapshot from state/manifest/media
    3. If render: prepare safe media symlinks in runtime shell
    4. Write bootstrap_snapshot.js atomically to runtime shell

    If render aliases fail → write hold snapshot (safe fallback).

    Args:
        root: Agent root path — has state/, manifest/, media/.
        source_shell_dir: Immutable shell source directory (e.g. /opt).
        runtime_shell_dir: Mutable runtime shell directory.
        stale_seconds: Max state age before stale (default 30s).
        now: Optional datetime for test time injection.

    Returns:
        KsoLocalVisualDemoPrepareResult — safe aggregate, never raises.
    """
    # ── Validate args ────────────────────────────────────────────
    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoLocalVisualDemoPrepareResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        source_dir = Path(source_shell_dir)
    except (TypeError, ValueError):
        return KsoLocalVisualDemoPrepareResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        runtime_dir = Path(runtime_shell_dir)
    except (TypeError, ValueError):
        return KsoLocalVisualDemoPrepareResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    if stale_seconds <= 0:
        return KsoLocalVisualDemoPrepareResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Step 1: Prepare runtime shell workspace ──────────────────
    try:
        ws_result = prepare_kso_runtime_shell_workspace(
            source_shell_dir=source_dir,
            runtime_shell_dir=runtime_dir,
        )
    except Exception:
        return KsoLocalVisualDemoPrepareResult(
            status=STATUS_ERROR,
            reason=REASON_WORKSPACE_FAILED,
        )

    if ws_result.status == WS_STATUS_ERROR:
        return KsoLocalVisualDemoPrepareResult(
            status=STATUS_ERROR,
            reason=REASON_WORKSPACE_FAILED,
            workspace_ready=False,
        )

    workspace_ready = ws_result.prepared

    # ── Step 2: Build shell snapshot ─────────────────────────────
    try:
        snapshot = build_kso_shell_snapshot(root, stale_seconds, now)
    except Exception:
        return KsoLocalVisualDemoPrepareResult(
            status=STATUS_ERROR,
            reason=REASON_SNAPSHOT_BUILD_FAILED,
            workspace_ready=workspace_ready,
        )

    snapshot_mode = snapshot.snapshot_mode
    media_alias_ready = False

    # ── Step 3: Prepare media aliases (render only) ──────────────
    if snapshot_mode == SNAPSHOT_MODE_RENDER:
        try:
            media_alias_ready = _prepare_media_aliases(
                root, runtime_dir, stale_seconds, now)
        except Exception:
            media_alias_ready = False

    # ── Step 4: Write bootstrap_snapshot.js ──────────────────────
    snapshot_written = False
    final_mode = snapshot_mode

    if snapshot_mode == SNAPSHOT_MODE_RENDER and not media_alias_ready:
        # Render mode but alias failed — force hold snapshot
        dst = runtime_dir / "bootstrap_snapshot.js"
        try:
            if _atomic_write_hold_snapshot(dst):
                snapshot_written = True
            final_mode = SNAPSHOT_MODE_HOLD
        except Exception:
            pass
    else:
        # Normal path: use the standard writer
        try:
            write_result = write_kso_runtime_bootstrap_snapshot(
                root=root,
                runtime_shell_dir=runtime_dir,
                stale_seconds=stale_seconds,
                now=now,
            )
            snapshot_written = write_result.written
            final_mode = write_result.snapshot_mode
        except Exception:
            pass

    if not snapshot_written:
        return KsoLocalVisualDemoPrepareResult(
            status=STATUS_ERROR,
            reason=REASON_SNAPSHOT_WRITE_FAILED,
            workspace_ready=workspace_ready,
            snapshot_mode=final_mode,
            media_alias_ready=media_alias_ready,
        )

    return KsoLocalVisualDemoPrepareResult(
        status=STATUS_OK,
        prepared=True,
        workspace_ready=workspace_ready,
        snapshot_written=True,
        snapshot_mode=final_mode,
        media_alias_ready=media_alias_ready,
        reason=REASON_PREPARED,
    )


def format_kso_local_visual_demo_prepare_result(
    result: KsoLocalVisualDemoPrepareResult,
) -> str:
    """Format result as a safe human-readable string.

    Never contains paths, filenames, mediaRef values, IDs, raw JSON,
    exception text, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"prepared: {str(result.prepared).lower()}",
        f"workspace_ready: {str(result.workspace_ready).lower()}",
        f"snapshot_written: {str(result.snapshot_written).lower()}",
        f"snapshot_mode: {result.snapshot_mode}",
        f"media_alias_ready: {str(result.media_alias_ready).lower()}",
        f"reason: {result.reason}",
    ]
    return "\n".join(lines)
