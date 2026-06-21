"""KSO Player Guarded Local Chromium Demo Runner — guarded launch wrapper.

Pipeline:
  prepare_kso_local_visual_demo → build Chromium command
    → (if confirm_launch) launch Chromium

Defaults to prepare-only (confirm_launch=False). Chromium launches ONLY
with explicit --confirm-launch via the injected process_launcher callable.

This is a demo runner — NOT production systemd, NOT installer, NOT PoP.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from kso_player.local_visual_demo_prepare import (
    prepare_kso_local_visual_demo,
    KsoLocalVisualDemoPrepareResult,
    SNAPSHOT_MODE_HOLD,
    SNAPSHOT_MODE_RENDER,
    STATUS_OK as PREPARE_STATUS_OK,
    STATUS_ERROR as PREPARE_STATUS_ERROR,
    FORBIDDEN_SUBSTRINGS,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

REASON_PREPARED_LAUNCH_READY = "prepared_launch_ready"
REASON_PREPARED_LAUNCHED = "prepared_launched"
REASON_PREPARE_FAILED = "prepare_failed"
REASON_LAUNCH_FAILED = "launch_failed"
REASON_INVALID_ARGS = "invalid_args"

WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 1080
WINDOW_POSITION_X = 0
WINDOW_POSITION_Y = 0

# Forbidden Chromium flags — MUST NOT appear in command
_FORBIDDEN_CHROMIUM_FLAGS = frozenset({
    "--disable-web-security",
    "--allow-file-access-from-files",
    "--allow-file-access",
    "--allow-running-insecure-content",
    "--disable-xss-auditor",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoLocalChromiumDemoRunnerResult:
    """Safe result of guarded local Chromium demo run.

    NEVER contains paths, file URLs, full commands, mediaRef values,
    IDs, raw JSON, exception text, or forbidden substrings.

    Internal fields (_command, _process) use repr=False.
    """

    status: str = STATUS_ERROR
    prepared: bool = False
    snapshot_mode: str = SNAPSHOT_MODE_HOLD
    media_alias_ready: bool = False
    launch_ready: bool = False
    launched: bool = False
    reason: str = REASON_INVALID_ARGS

    # Internal — NEVER exposed in safe output
    _command: List[str] = field(default_factory=list, repr=False)
    _process: object = field(default=None, repr=False)

    def __repr__(self) -> str:
        return (
            f"KsoLocalChromiumDemoRunnerResult("
            f"status={self.status!r}, "
            f"prepared={self.prepared}, "
            f"snapshot_mode={self.snapshot_mode!r}, "
            f"media_alias_ready={self.media_alias_ready}, "
            f"launch_ready={self.launch_ready}, "
            f"launched={self.launched}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _build_chromium_command(
    chromium_bin: str,
    runtime_shell_dir: Path,
    window_width: int = WINDOW_WIDTH,
    window_height: int = WINDOW_HEIGHT,
    window_x: int = WINDOW_POSITION_X,
    window_y: int = WINDOW_POSITION_Y,
) -> List[str]:
    """Build a safe Chromium command as a list of args.

    Uses --app=file:// for a windowed app-like experience.
    NO shell=True, NO external URLs, NO forbidden flags.

    Returns:
        List of string args — NEVER a shell string.
    """
    index_path = runtime_shell_dir / "index.html"
    file_url = f"file://{index_path}"
    profile_dir = runtime_shell_dir / "chromium-profile"

    return [
        chromium_bin,
        f"--app={file_url}",
        f"--window-size={window_width},{window_height}",
        f"--window-position={window_x},{window_y}",
        "--no-first-run",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-translate",
        "--disable-default-apps",
        f"--user-data-dir={profile_dir}",
    ]


def _validate_command_forbidden_flags(command: List[str]) -> bool:
    """Check command does not contain any forbidden Chromium flags."""
    for arg in command:
        # Parse flag name (before = if present)
        flag = arg.split("=", 1)[0]
        if flag in _FORBIDDEN_CHROMIUM_FLAGS:
            return False
    return True


def _default_process_launcher(command: Sequence[str]) -> Optional[object]:
    """Default process launcher — uses subprocess.Popen.

    Called ONLY when confirm_launch=True.
    Returns Popen object or None on failure.
    """
    import subprocess

    try:
        return subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def prepare_and_maybe_launch_kso_local_chromium_demo(
    root,
    source_shell_dir,
    runtime_shell_dir,
    chromium_bin: str,
    confirm_launch: bool = False,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
    process_launcher: Optional[Callable[[List[str]], Optional[object]]] = None,
) -> KsoLocalChromiumDemoRunnerResult:
    """Prepare demo and optionally launch Chromium.

    Full pipeline:
    1. prepare_kso_local_visual_demo(root, source, runtime)
    2. If prepare failed → return error, no launch
    3. Build Chromium command (internal only)
    4. If confirm_launch=False → return launch_ready=True, launched=False
    5. If confirm_launch=True → call process_launcher(command)

    Args:
        root: Agent root path.
        source_shell_dir: Immutable shell source directory.
        runtime_shell_dir: Mutable runtime shell directory.
        chromium_bin: Chromium binary path/name (e.g. 'chromium').
        confirm_launch: If True, actually launch Chromium (default False).
        stale_seconds: Max state age before stale (default 30s).
        now: Optional datetime for test time injection.
        process_launcher: Optional callable(command: List[str]) → Popen|None.
            Defaults to subprocess.Popen with DEVNULL stdio.

    Returns:
        KsoLocalChromiumDemoRunnerResult — safe aggregate, never raises.
    """
    # ── Validate args ────────────────────────────────────────────
    if not isinstance(chromium_bin, str) or not chromium_bin.strip():
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    if stale_seconds <= 0:
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        source_dir = Path(source_shell_dir)
    except (TypeError, ValueError):
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        runtime_dir = Path(runtime_shell_dir)
    except (TypeError, ValueError):
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Step 1: Prepare demo ─────────────────────────────────────
    try:
        prepare_result = prepare_kso_local_visual_demo(
            root=root,
            source_shell_dir=source_dir,
            runtime_shell_dir=runtime_dir,
            stale_seconds=stale_seconds,
            now=now,
        )
    except Exception:
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            reason=REASON_PREPARE_FAILED,
        )

    if prepare_result.status == PREPARE_STATUS_ERROR:
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            reason=REASON_PREPARE_FAILED,
            snapshot_mode=prepare_result.snapshot_mode,
            media_alias_ready=prepare_result.media_alias_ready,
        )

    # ── Step 2: Build Chromium command ────────────────────────────
    try:
        command = _build_chromium_command(chromium_bin, runtime_dir)
    except Exception:
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            reason=REASON_PREPARE_FAILED,
            prepared=True,
            snapshot_mode=prepare_result.snapshot_mode,
            media_alias_ready=prepare_result.media_alias_ready,
        )

    # Validate command against forbidden flags
    if not _validate_command_forbidden_flags(command):
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
            prepared=True,
            snapshot_mode=prepare_result.snapshot_mode,
            media_alias_ready=prepare_result.media_alias_ready,
        )

    launch_ready = True

    # ── Step 3: Conditional launch ────────────────────────────────
    if not confirm_launch:
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_OK,
            prepared=True,
            snapshot_mode=prepare_result.snapshot_mode,
            media_alias_ready=prepare_result.media_alias_ready,
            launch_ready=launch_ready,
            launched=False,
            reason=REASON_PREPARED_LAUNCH_READY,
            _command=command,
        )

    # confirm_launch=True: actually launch
    launcher = process_launcher or _default_process_launcher

    try:
        proc = launcher(command)
        if proc is None:
            return KsoLocalChromiumDemoRunnerResult(
                status=STATUS_ERROR,
                prepared=True,
                snapshot_mode=prepare_result.snapshot_mode,
                media_alias_ready=prepare_result.media_alias_ready,
                launch_ready=launch_ready,
                launched=False,
                reason=REASON_LAUNCH_FAILED,
            )

        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_OK,
            prepared=True,
            snapshot_mode=prepare_result.snapshot_mode,
            media_alias_ready=prepare_result.media_alias_ready,
            launch_ready=launch_ready,
            launched=True,
            reason=REASON_PREPARED_LAUNCHED,
            _command=command,
            _process=proc,
        )
    except Exception:
        return KsoLocalChromiumDemoRunnerResult(
            status=STATUS_ERROR,
            prepared=True,
            snapshot_mode=prepare_result.snapshot_mode,
            media_alias_ready=prepare_result.media_alias_ready,
            launch_ready=launch_ready,
            launched=False,
            reason=REASON_LAUNCH_FAILED,
        )


def format_kso_local_chromium_demo_runner_result(
    result: KsoLocalChromiumDemoRunnerResult,
) -> str:
    """Format result as a safe human-readable string.

    Never contains paths, file URLs, full commands, mediaRef values,
    IDs, raw JSON, exception text, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"prepared: {str(result.prepared).lower()}",
        f"snapshot_mode: {result.snapshot_mode}",
        f"media_alias_ready: {str(result.media_alias_ready).lower()}",
        f"launch_ready: {str(result.launch_ready).lower()}",
        f"launched: {str(result.launched).lower()}",
        f"reason: {result.reason}",
    ]
    return "\n".join(lines)
