"""KSO Player Shell Command Core — safe bridge from render plan to HTML shell.

Converts a render plan into a safe command for the future Chromium kiosk
HTML shell (window.KsoPlayerShell API).

Pipeline: runtime_gate → runtime_decision → render_plan → shell_command

The command carries only safe fields (mediaType, durationBucket).
NO paths, NO filenames, NO media src, NO manifest IDs, NO hashes.

NO Chromium, NO HTTP, NO PoP write, NO backend.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from kso_player.render_plan import (
    build_kso_render_plan,
    KsoRenderPlanResult,
    RENDER_ACTION_RENDER,
    RENDER_ACTION_HOLD,
    MEDIA_IMAGE,
    MEDIA_VIDEO,
    MEDIA_UNKNOWN,
    FORBIDDEN_SUBSTRINGS,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

SHELL_MODE_HOLD = "hold"
SHELL_MODE_RENDER = "render"

COMMAND_HOLD = "hold"
COMMAND_SET_RENDER_PLAN = "setRenderPlan"
COMMAND_CLEAR = "clear"

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

# ── Reasons ─────────────────────────────────────────────────────────

REASON_READY_FOR_SHELL = "ready_for_shell"
REASON_RENDER_PLAN_HOLD = "render_plan_hold"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoShellCommandResult:
    """Safe shell command for the HTML shell (window.KsoPlayerShell API).

    Carry only safe fields: mode, mediaType, durationBucket.
    NEVER: paths, filenames, media src, manifest IDs, hashes.
    """

    status: str = STATUS_ERROR
    shell_mode: str = SHELL_MODE_HOLD
    command: str = COMMAND_HOLD
    reason: str = REASON_INVALID_ARGS
    render_action: str = RENDER_ACTION_HOLD
    media_type: str = MEDIA_UNKNOWN
    duration_bucket: str = "unknown"
    pop_event_should_be_written: bool = False

    def __repr__(self) -> str:
        return (
            f"KsoShellCommandResult("
            f"status={self.status!r}, "
            f"shell_mode={self.shell_mode!r}, "
            f"command={self.command!r}, "
            f"reason={self.reason!r}, "
            f"render_action={self.render_action!r}, "
            f"media_type={self.media_type!r}, "
            f"duration_bucket={self.duration_bucket!r}, "
            f"pop_event_should_be_written={self.pop_event_should_be_written})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def build_kso_shell_command(
    root,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
) -> KsoShellCommandResult:
    """Build a safe shell command from render plan.

    Pipeline: render_plan → shell_command.

    If render_action == "render": shell_mode="render", command="setRenderPlan"
    with safe fields (mediaType, durationBucket only — NO paths/IDs/hashes).

    If render_action != "render": shell_mode="hold", command="hold".

    Args:
        root: Agent root path (str or Path).
        stale_seconds: Max state age before stale (default 30s).
        now: Optional datetime for test time injection.

    Returns:
        KsoShellCommandResult — safe aggregate, never raises.
    """
    # ── Validate args ────────────────────────────────────────────
    if stale_seconds <= 0:
        return KsoShellCommandResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoShellCommandResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Build render plan ────────────────────────────────────────
    try:
        render_plan = build_kso_render_plan(root, stale_seconds, now)
    except Exception:
        return KsoShellCommandResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
        )

    # ── Hold path ────────────────────────────────────────────────
    if render_plan.render_action != RENDER_ACTION_RENDER:
        return KsoShellCommandResult(
            status=render_plan.status,
            shell_mode=SHELL_MODE_HOLD,
            command=COMMAND_HOLD,
            reason=REASON_RENDER_PLAN_HOLD,
            render_action=render_plan.render_action,
        )

    # ── Render path ──────────────────────────────────────────────
    return KsoShellCommandResult(
        status=STATUS_OK,
        shell_mode=SHELL_MODE_RENDER,
        command=COMMAND_SET_RENDER_PLAN,
        reason=REASON_READY_FOR_SHELL,
        render_action=RENDER_ACTION_RENDER,
        media_type=render_plan.media_type,
        duration_bucket=render_plan.duration_bucket,
        pop_event_should_be_written=True,
    )


def format_kso_shell_command_result(result: KsoShellCommandResult) -> str:
    """Format a KsoShellCommandResult as a safe human-readable string.

    Never contains paths, filenames, IDs, hashes, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"shell_mode: {result.shell_mode}",
        f"command: {result.command}",
        f"reason: {result.reason}",
        f"render_action: {result.render_action}",
        f"media_type: {result.media_type}",
        f"duration_bucket: {result.duration_bucket}",
        f"pop_event_should_be_written: "
        f"{str(result.pop_event_should_be_written).lower()}",
    ]
    return "\n".join(lines)
