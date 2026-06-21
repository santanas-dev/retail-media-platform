"""KSO Player Timed Runtime Cycle Core — prepare, wait, re-check, write PoP.

Pipeline:
  1. (optional) prepare_demo_fixture
  2. visible_runtime (prepare + optionally launch Chromium)
  3. If hold → return hold result
  4. Get duration_ms from render plan's selected item
  5. If confirm_display_completed:
     a. Sleep via injectable sleep_fn (clamped to safe range)
     b. Re-check runtime gate — state still idle + fresh?
     c. If state changed/stale → NO completed PoP
     d. If state still idle → write completed PoP

This is NOT a systemd service — one controlled cycle.
Production daemon will call this continuously in a future step.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from kso_player.visible_runtime import (
    run_kso_visible_runtime_once,
    KsoVisibleRuntimeResult,
    STATUS_OK as VR_STATUS_OK,
    STATUS_ERROR as VR_STATUS_ERROR,
    REASON_READY,
    REASON_HOLD,
    FORBIDDEN_SUBSTRINGS,
)
from kso_player.shell_snapshot import (
    SNAPSHOT_MODE_RENDER,
)
from kso_player.runtime_gate import (
    evaluate_kso_runtime_gate,
    ACTION_PLAY as GATE_PLAY,
)
from kso_player.render_plan import (
    build_kso_render_plan,
    RENDER_ACTION_RENDER,
)
from kso_player.events import (
    build_playback_event_completed,
)
from kso_player.simulator import simulate_playback_step, SIM_STATUS_WOULD_PLAY
from kso_player.safety import PlaybackSafetySnapshot, decide_playback_safety
from kso_player.playlist import build_playlist
from kso_player.pop_writer import (
    write_pop_event,
    STATUS_WRITTEN,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_ERROR = "error"

REASON_RUNTIME_READY = "runtime_ready"
REASON_RUNTIME_LAUNCHED = "runtime_launched"
REASON_RUNTIME_HOLD = "runtime_hold"
REASON_RUNTIME_COMPLETED = "runtime_completed_pop_written"
REASON_NO_COMPLETED_CONFIRM = "runtime_no_completed_confirm"
REASON_STATE_CHANGED = "state_changed_during_display"
REASON_STATE_STALE = "state_stale_during_display"
REASON_NO_RENDER_READY = "render_not_ready"
REASON_FIXTURE_FAILED = "fixture_failed"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"

# Duration clamping for runtime-cycle-once
DURATION_MS_MIN = 1000       # 1 second minimum
DURATION_MS_MAX = 60000      # 60 seconds maximum (1 minute)


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoRuntimeCycleResult:
    """Safe result of one timed runtime cycle.

    NEVER contains absolute paths, file URLs, full Chromium commands,
    mediaRef values, IDs, raw JSON, exception text, or forbidden substrings.

    Internal fields (_visible_result) use repr=False.
    """

    status: str = STATUS_ERROR
    fixture_ready: bool = False
    render_ready: bool = False
    shell_prepared: bool = False
    snapshot_written: bool = False
    launch_ready: bool = False
    launched: bool = False
    display_waited: bool = False
    state_rechecked: bool = False
    completed_pop_write_requested: bool = False
    completed_pop_written: bool = False
    reason: str = REASON_INVALID_ARGS

    # Internal — NEVER exposed in safe output
    _visible_result: Optional[KsoVisibleRuntimeResult] = field(
        default=None, repr=False,
    )

    def __repr__(self) -> str:
        return (
            f"KsoRuntimeCycleResult("
            f"status={self.status!r}, "
            f"fixture_ready={self.fixture_ready}, "
            f"render_ready={self.render_ready}, "
            f"shell_prepared={self.shell_prepared}, "
            f"snapshot_written={self.snapshot_written}, "
            f"launch_ready={self.launch_ready}, "
            f"launched={self.launched}, "
            f"display_waited={self.display_waited}, "
            f"state_rechecked={self.state_rechecked}, "
            f"completed_pop_write_requested={self.completed_pop_write_requested}, "
            f"completed_pop_written={self.completed_pop_written}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Default sleep (production — uses time.sleep)
# ══════════════════════════════════════════════════════════════════════

def _default_sleep_fn(seconds: float) -> None:
    """Default sleep implementation — uses time.sleep.

    Used in production CLI. Tests inject their own sleep_fn.
    """
    import time
    time.sleep(seconds)


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_kso_runtime_cycle_once(
    root,
    source_shell_dir,
    runtime_shell_dir,
    chromium_bin: str,
    confirm_launch: bool = False,
    confirm_display_completed: bool = False,
    prepare_demo_fixture: bool = False,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    process_launcher: Optional[Callable[[List[str]], Optional[object]]] = None,
) -> KsoRuntimeCycleResult:
    """Run one timed KSO runtime cycle: prepare → launch → wait → re-check → PoP.

    Full pipeline:
    1. If prepare_demo_fixture: create demo root
    2. visible_runtime (prepare shell + snapshot + optionally launch Chromium)
    3. If hold → return hold result (no Chromium, no PoP)
    4. Extract duration_ms from render plan's selected item (clamped to 1-60s)
    5. If confirm_display_completed:
       a. Wait duration via sleep_fn
       b. Re-check runtime gate (state still idle + fresh?)
       c. If state changed/stale → NO completed PoP
       d. If state still idle → write completed PoP

    PoP is NEVER written without explicit confirm_display_completed=True.
    This is NOT a systemd service — one controlled cycle for testing/demo.

    Args:
        root: Agent root path (str or Path).
        source_shell_dir: Immutable shell source directory.
        runtime_shell_dir: Mutable runtime shell directory.
        chromium_bin: Chromium binary path/name.
        confirm_launch: Actually launch Chromium.
        confirm_display_completed: Wait + re-check state + write completed PoP.
        prepare_demo_fixture: Auto-create demo root.
        stale_seconds: Max state age before stale (default 30s).
        now: Optional datetime for test time injection.
        sleep_fn: Optional callable(seconds: float) for sleep (test injection).
        process_launcher: Optional callable for Chromium launch (test injection).

    Returns:
        KsoRuntimeCycleResult — always safe, never raises.
    """
    if sleep_fn is None:
        sleep_fn = _default_sleep_fn

    # ── Validate common args ──────────────────────────────────────
    if not isinstance(chromium_bin, str) or not chromium_bin.strip():
        return KsoRuntimeCycleResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    if stale_seconds <= 0:
        return KsoRuntimeCycleResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoRuntimeCycleResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Step 1-2: Prepare + optionally launch via visible_runtime ─
    try:
        visible_result = run_kso_visible_runtime_once(
            root=root,
            source_shell_dir=source_shell_dir,
            runtime_shell_dir=runtime_shell_dir,
            chromium_bin=chromium_bin,
            confirm_launch=confirm_launch,
            prepare_demo_fixture=prepare_demo_fixture,
            stale_seconds=stale_seconds,
            now=now,
            process_launcher=process_launcher,
        )
    except Exception:
        return KsoRuntimeCycleResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
        )

    if visible_result.status == VR_STATUS_ERROR:
        return KsoRuntimeCycleResult(
            status=STATUS_ERROR,
            reason=visible_result.reason,
            fixture_ready=visible_result.fixture_ready,
            render_ready=visible_result.render_ready,
            shell_prepared=visible_result.shell_prepared,
            snapshot_written=visible_result.snapshot_written,
            launch_ready=visible_result.launch_ready,
            launched=visible_result.launched,
            _visible_result=visible_result,
        )

    # ── Step 3: Check render readiness ──────────────────────────
    if not visible_result.render_ready:
        return KsoRuntimeCycleResult(
            status=STATUS_OK,
            reason=REASON_RUNTIME_HOLD,
            fixture_ready=visible_result.fixture_ready,
            render_ready=False,
            shell_prepared=visible_result.shell_prepared,
            snapshot_written=visible_result.snapshot_written,
            launch_ready=visible_result.launch_ready,
            launched=visible_result.launched,
            _visible_result=visible_result,
        )

    # ── Step 4: Extract duration_ms from render plan ────────────
    duration_ms = _extract_duration_ms(root, stale_seconds, now)

    # ── Step 5: Build base result ─────────────────────────────
    base = KsoRuntimeCycleResult(
        status=STATUS_OK,
        fixture_ready=visible_result.fixture_ready,
        render_ready=True,
        shell_prepared=visible_result.shell_prepared,
        snapshot_written=visible_result.snapshot_written,
        launch_ready=visible_result.launch_ready,
        launched=visible_result.launched,
        _visible_result=visible_result,
    )

    if not confirm_display_completed:
        base.reason = REASON_NO_COMPLETED_CONFIRM
        return base

    # ── Step 6: Wait display duration ─────────────────────────
    base.completed_pop_write_requested = True

    try:
        sleep_seconds = duration_ms / 1000.0
        sleep_fn(sleep_seconds)
        base.display_waited = True
    except Exception:
        base.reason = REASON_INTERNAL_ERROR
        return base

    # ── Step 7: Re-check runtime gate ─────────────────────────
    base.state_rechecked = True

    try:
        gate_after = evaluate_kso_runtime_gate(root, stale_seconds, now)
    except Exception:
        base.reason = REASON_INTERNAL_ERROR
        return base

    # State must still be idle + fresh
    if gate_after.action != GATE_PLAY:
        if not gate_after.fresh:
            base.reason = REASON_STATE_STALE
        else:
            base.reason = REASON_STATE_CHANGED
        return base

    # ── Step 8: Write completed PoP ───────────────────────────
    try:
        safety_state = gate_after.state
        playlist = build_playlist(root)
        snapshot = PlaybackSafetySnapshot(state=safety_state)
        safety_decision = decide_playback_safety(snapshot, playlist)
        sim_result = simulate_playback_step(
            playlist, safety_decision, session_state=None,
        )
        event_completed = build_playback_event_completed(sim_result)
    except Exception:
        base.reason = REASON_INTERNAL_ERROR
        return base

    try:
        pop_result = write_pop_event(root, event_completed, safety_state)
    except Exception:
        base.reason = REASON_INTERNAL_ERROR
        return base

    if pop_result.status == STATUS_WRITTEN:
        base.completed_pop_written = True
        base.reason = REASON_RUNTIME_COMPLETED
    else:
        base.reason = pop_result.reason

    return base


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _extract_duration_ms(
    root: Path,
    stale_seconds: int,
    now: Optional[datetime],
) -> int:
    """Extract duration_ms from render plan's selected item, clamped to safe range.

    Returns:
        duration_ms clamped to [1000, 60000].
    """
    duration_ms = DURATION_MS_MIN  # safe default

    try:
        plan = build_kso_render_plan(root, stale_seconds, now)
        if plan.render_action != RENDER_ACTION_RENDER:
            return DURATION_MS_MIN

        item = plan._selected_item
        if item is not None and hasattr(item, "duration_ms"):
            raw = getattr(item, "duration_ms", 0)
            if isinstance(raw, (int, float)) and raw > 0:
                duration_ms = min(max(int(raw), DURATION_MS_MIN), DURATION_MS_MAX)
    except Exception:
        # Safe fallback — use minimum
        pass

    return duration_ms


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_kso_runtime_cycle_result(result: KsoRuntimeCycleResult) -> str:
    """Format result as a safe human-readable string.

    NEVER contains absolute paths, file URLs, full Chromium commands,
    mediaRef values, IDs, raw JSON, exception text, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"fixture_ready: {str(result.fixture_ready).lower()}",
        f"render_ready: {str(result.render_ready).lower()}",
        f"shell_prepared: {str(result.shell_prepared).lower()}",
        f"snapshot_written: {str(result.snapshot_written).lower()}",
        f"launch_ready: {str(result.launch_ready).lower()}",
        f"launched: {str(result.launched).lower()}",
        f"display_waited: {str(result.display_waited).lower()}",
        f"state_rechecked: {str(result.state_rechecked).lower()}",
        f"completed_pop_write_requested: {str(result.completed_pop_write_requested).lower()}",
        f"completed_pop_written: {str(result.completed_pop_written).lower()}",
        f"reason: {result.reason}",
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
