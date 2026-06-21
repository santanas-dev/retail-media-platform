"""KSO Player Production Daemon Loop Core — long-running player process.

Pipeline:
  1. Prepare runtime shell once
  2. Optionally launch Chromium once
  3. Enter daemon loop:
     a. Check stop_check() before each cycle
     b. Build playlist (re-read manifest each cycle for updates)
     c. Check gate → hold if not idle
     d. Select next item (round-robin)
     e. Write live snapshot → shell auto-refreshes
     f. Wait duration
     g. Re-check gate → if idle + confirm → completed PoP
     h. On error → increment error_count, check limit
     i. Write health file if configured
  4. Return safe result on stop

NO systemd, NO backend, NO sidecar. Completed PoP NEVER automatic.
This is NOT a systemd service yet — systemd unit comes later.
"""

import json as _json
import os as _os
import tempfile as _tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from kso_player.visible_runtime import (
    run_kso_visible_runtime_once,
    KsoVisibleRuntimeResult,
    STATUS_OK as VR_STATUS_OK,
    STATUS_ERROR as VR_STATUS_ERROR,
    FORBIDDEN_SUBSTRINGS,
)
from kso_player.runtime_gate import (
    evaluate_kso_runtime_gate,
    ACTION_PLAY as GATE_PLAY,
)
from kso_player.playlist import build_playlist, PlayerPlaylistItem
from kso_player.simulator import simulate_playback_step
from kso_player.safety import PlaybackSafetySnapshot, decide_playback_safety
from kso_player.events import build_playback_event_completed
from kso_player.pop_writer import write_pop_event
from kso_player.runtime_loop import (
    _write_hold_snapshot,
    _write_item_snapshot,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_ERROR = "error"

REASON_STOPPED = "daemon_stopped"
REASON_STOP_CHECK = "stop_check_triggered"
REASON_MAX_ERRORS = "max_consecutive_errors_exceeded"
REASON_PREPARE_FAILED = "prepare_failed"
REASON_NO_ITEMS = "no_playable_items"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"

DURATION_MS_MIN = 1000
DURATION_MS_MAX = 60000
DEFAULT_MAX_CONSECUTIVE_ERRORS = 3

# Forbidden in safe output
_FORBIDDEN = FORBIDDEN_SUBSTRINGS


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoRuntimeDaemonResult:
    """Safe result of daemon loop execution.

    NEVER contains absolute paths, file URLs, mediaRef values,
    IDs, raw JSON, exception text, or forbidden substrings.
    """

    status: str = STATUS_ERROR
    fixture_ready: bool = False
    shell_prepared: bool = False
    launch_ready: bool = False
    launched: bool = False
    cycles_completed: int = 0
    rendered_count: int = 0
    hold_count: int = 0
    error_count: int = 0
    completed_pop_write_requested: bool = False
    completed_pop_written_count: int = 0
    items_in_playlist: int = 0
    reason: str = REASON_INVALID_ARGS
    last_cycle_status: str = ""

    _visible_result: Optional[KsoVisibleRuntimeResult] = field(
        default=None, repr=False,
    )

    def __repr__(self) -> str:
        return (
            f"KsoRuntimeDaemonResult("
            f"status={self.status!r}, "
            f"fixture_ready={self.fixture_ready}, "
            f"shell_prepared={self.shell_prepared}, "
            f"launch_ready={self.launch_ready}, "
            f"launched={self.launched}, "
            f"cycles_completed={self.cycles_completed}, "
            f"rendered_count={self.rendered_count}, "
            f"hold_count={self.hold_count}, "
            f"error_count={self.error_count}, "
            f"completed_pop_write_requested={self.completed_pop_write_requested}, "
            f"completed_pop_written_count={self.completed_pop_written_count}, "
            f"items_in_playlist={self.items_in_playlist}, "
            f"last_cycle_status={self.last_cycle_status!r}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Default sleep
# ══════════════════════════════════════════════════════════════════════

def _default_sleep_fn(seconds: float) -> None:
    import time
    time.sleep(seconds)


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def run_kso_runtime_daemon(
    root,
    source_shell_dir,
    runtime_shell_dir,
    chromium_bin: str,
    confirm_launch: bool = False,
    confirm_display_completed: bool = False,
    prepare_demo_fixture: bool = False,
    max_cycles: Optional[int] = None,
    cycle_pause_seconds: float = 0,
    stop_check: Optional[Callable[[], bool]] = None,
    max_consecutive_errors: int = DEFAULT_MAX_CONSECUTIVE_ERRORS,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    process_launcher: Optional[Callable[[List[str]], Optional[object]]] = None,
    health_file: Optional[str] = None,
) -> KsoRuntimeDaemonResult:
    """Run the KSO player as a long-running daemon process.

    Prepares once, then runs cycles continuously until stopped via
    stop_check, max_cycles, or max_consecutive_errors.

    max_cycles=None → daemon mode (runs until stop_check triggers).
    In tests, always use max_cycles or stop_check to avoid infinite loops.

    Args:
        root: Agent root path.
        source_shell_dir: Immutable shell source directory.
        runtime_shell_dir: Mutable runtime shell directory.
        chromium_bin: Chromium binary path/name.
        confirm_launch: Actually launch Chromium (once).
        confirm_display_completed: Write completed PoP after successful cycles.
        prepare_demo_fixture: Auto-create demo root.
        max_cycles: Max cycles (None = daemon mode, 0 = no-op).
        cycle_pause_seconds: Pause between cycles (future use, default 0).
        stop_check: Callable → True to stop cleanly (test injection).
        max_consecutive_errors: Stop after this many consecutive errors (default 3).
        stale_seconds: Max state age before stale.
        now: Optional datetime for test time injection.
        sleep_fn: Injectable sleep.
        process_launcher: Injectable Chromium launcher.
        health_file: Optional path to safe health JSON file.

    Returns:
        KsoRuntimeDaemonResult — always safe, never raises.
    """
    if sleep_fn is None:
        sleep_fn = _default_sleep_fn

    # ── Validate args ──────────────────────────────────────────
    if not isinstance(chromium_bin, str) or not chromium_bin.strip():
        return KsoRuntimeDaemonResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)
    if stale_seconds <= 0:
        return KsoRuntimeDaemonResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)
    if max_cycles is not None and max_cycles < 0:
        return KsoRuntimeDaemonResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)
    if max_consecutive_errors < 1:
        return KsoRuntimeDaemonResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoRuntimeDaemonResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)

    try:
        runtime_dir = Path(runtime_shell_dir)
    except (TypeError, ValueError):
        return KsoRuntimeDaemonResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)

    # ── Initialize once ────────────────────────────────────────
    try:
        visible_result = run_kso_visible_runtime_once(
            root=root, source_shell_dir=source_shell_dir,
            runtime_shell_dir=runtime_shell_dir, chromium_bin=chromium_bin,
            confirm_launch=confirm_launch,
            prepare_demo_fixture=prepare_demo_fixture,
            stale_seconds=stale_seconds, now=now,
            process_launcher=process_launcher,
        )
    except Exception:
        return KsoRuntimeDaemonResult(status=STATUS_ERROR, reason=REASON_INTERNAL_ERROR)

    if visible_result.status == VR_STATUS_ERROR:
        return KsoRuntimeDaemonResult(
            status=STATUS_ERROR, reason=REASON_PREPARE_FAILED,
            fixture_ready=visible_result.fixture_ready,
            shell_prepared=visible_result.shell_prepared,
            launch_ready=visible_result.launch_ready,
            launched=visible_result.launched,
            _visible_result=visible_result,
        )

    result = KsoRuntimeDaemonResult(
        status=STATUS_OK,
        fixture_ready=visible_result.fixture_ready,
        shell_prepared=visible_result.shell_prepared,
        launch_ready=visible_result.launch_ready,
        launched=visible_result.launched,
        completed_pop_write_requested=confirm_display_completed,
        reason=REASON_STOPPED,
        _visible_result=visible_result,
    )

    # ── max_cycles=0 → immediate no-op ─────────────────────────
    if max_cycles is not None and max_cycles == 0:
        return result

    # ── Daemon loop ────────────────────────────────────────────
    cycle = 0
    consecutive_errors = 0

    while True:
        # Check stop before cycle
        if stop_check is not None:
            try:
                if stop_check():
                    result.reason = REASON_STOP_CHECK
                    result.last_cycle_status = "stopped"
                    _write_health(result, health_file)
                    return result
            except Exception:
                pass  # ignore stop_check errors

        # Check max_cycles
        if max_cycles is not None and cycle >= max_cycles:
            result.reason = REASON_STOPPED
            _write_health(result, health_file)
            return result

        # ── Run one cycle ──────────────────────────────────
        cycle_status = ""
        try:
            cycle_status = _run_one_daemon_cycle(
                root=root, runtime_dir=runtime_dir, cycle=cycle,
                stale_seconds=stale_seconds, now=now,
                confirm_display_completed=confirm_display_completed,
                sleep_fn=sleep_fn,
            )
        except Exception:
            cycle_status = "error"
            consecutive_errors += 1
            result.error_count += 1

            if consecutive_errors >= max_consecutive_errors:
                result.status = STATUS_ERROR
                result.reason = REASON_MAX_ERRORS
                result.last_cycle_status = "error"
                _write_health(result, health_file)
                return result
            # Continue to next cycle
            cycle += 1
            if cycle_pause_seconds > 0:
                try:
                    sleep_fn(cycle_pause_seconds)
                except Exception:
                    pass
            continue

        # ── Process cycle outcome ──────────────────────────
        result.cycles_completed += 1
        result.last_cycle_status = cycle_status

        if cycle_status == "rendered":
            result.rendered_count += 1
            consecutive_errors = 0
        elif cycle_status == "rendered_with_pop":
            result.rendered_count += 1
            result.completed_pop_written_count += 1
            consecutive_errors = 0
        elif cycle_status == "hold":
            result.hold_count += 1
            consecutive_errors = 0
        elif cycle_status == "no_items":
            # Recoverable — wait, try again next cycle
            consecutive_errors = 0
        else:
            # Unknown status — treat as error
            consecutive_errors += 1
            result.error_count += 1

        # ══════════════════════════════════════════════════════
        # Write health file after each cycle
        # ══════════════════════════════════════════════════════
        _write_health(result, health_file)

        # Cycle pause
        if cycle_pause_seconds > 0:
            try:
                sleep_fn(cycle_pause_seconds)
            except Exception:
                pass

        cycle += 1

    # Unreachable — but safe return
    _write_health(result, health_file)
    return result


# ══════════════════════════════════════════════════════════════════════
# Single cycle runner
# ══════════════════════════════════════════════════════════════════════

def _run_one_daemon_cycle(
    root: Path,
    runtime_dir: Path,
    cycle: int,
    stale_seconds: int,
    now: Optional[datetime],
    confirm_display_completed: bool,
    sleep_fn: Callable[[float], None],
) -> str:
    """Run one daemon cycle. Returns cycle status string.

    Returns: "rendered_with_pop" | "rendered" | "hold" | "no_items" | "error"
    """
    # Build playlist fresh each cycle (manifest may have updated)
    playlist = build_playlist(root)
    if not playlist.ready or not playlist.items:
        _write_hold_snapshot(runtime_dir)
        return "no_items"

    items = playlist.items
    item_count = len(items)

    # Check gate
    gate_before = evaluate_kso_runtime_gate(root, stale_seconds, now)
    if gate_before.action != GATE_PLAY:
        _write_hold_snapshot(runtime_dir)
        return "hold"

    # Select item
    item_index = cycle % item_count
    item = items[item_index]

    # Write render snapshot
    _write_item_snapshot(runtime_dir, item)

    # Wait
    duration_ms = item.duration_ms if item.duration_ms > 0 else DURATION_MS_MIN
    duration_ms = min(max(duration_ms, DURATION_MS_MIN), DURATION_MS_MAX)
    sleep_fn(duration_ms / 1000.0)

    # Re-check gate
    gate_after = evaluate_kso_runtime_gate(root, stale_seconds, now)
    if gate_after.action != GATE_PLAY:
        # State changed → rendered but no PoP
        return "rendered"

    # Write completed PoP if confirmed
    if confirm_display_completed:
        _write_completed_pop(root, item, gate_after.state)
        return "rendered_with_pop"

    return "rendered"


# ══════════════════════════════════════════════════════════════════════
# Completed PoP writer
# ══════════════════════════════════════════════════════════════════════

def _write_completed_pop(
    root: Path, item: PlayerPlaylistItem, safety_state: str,
) -> None:
    """Write a completed PoP event. Fail-silent."""
    try:
        playlist = build_playlist(root)
        snapshot = PlaybackSafetySnapshot(state=safety_state)
        safety_decision = decide_playback_safety(snapshot, playlist)
        sim_result = simulate_playback_step(
            playlist, safety_decision, session_state=None,
        )
        event = build_playback_event_completed(sim_result)
        write_pop_event(root, event, safety_state)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
# Health file writer
# ══════════════════════════════════════════════════════════════════════

def _write_health(result: KsoRuntimeDaemonResult, health_file: Optional[str]) -> None:
    """Write safe health JSON atomically. Only safe fields — no paths/IDs/secrets."""
    if not health_file:
        return

    try:
        hp = Path(health_file)
    except (TypeError, ValueError):
        return

    data = {
        "status": result.status if result.status == STATUS_OK else result.status,
        "last_cycle_status": result.last_cycle_status,
        "cycles_completed": result.cycles_completed,
        "rendered_count": result.rendered_count,
        "hold_count": result.hold_count,
        "error_count": result.error_count,
        "completed_pop_written_count": result.completed_pop_written_count,
        "last_reason": result.reason,
    }

    json_str = _json.dumps(data, sort_keys=True, indent=2)

    # Safety: forbid sensitive data in health file
    lower = json_str.lower()
    for fb in _FORBIDDEN:
        if fb in lower:
            return  # Reject — don't write unsafe data

    try:
        hp.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = _tempfile.mkstemp(
            dir=str(hp.parent), prefix=".player-health.", suffix=".tmp",
        )
        try:
            _os.write(fd, json_str.encode("utf-8"))
            _os.fsync(fd)
        finally:
            _os.close(fd)
        _os.replace(tmp, str(hp))
    except OSError:
        pass


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_kso_runtime_daemon_result(result: KsoRuntimeDaemonResult) -> str:
    """Format result as a safe human-readable string.

    NEVER contains paths, file URLs, mediaRef values, IDs,
    raw JSON, exception text, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"fixture_ready: {str(result.fixture_ready).lower()}",
        f"shell_prepared: {str(result.shell_prepared).lower()}",
        f"launch_ready: {str(result.launch_ready).lower()}",
        f"launched: {str(result.launched).lower()}",
        f"cycles_completed: {result.cycles_completed}",
        f"rendered_count: {result.rendered_count}",
        f"hold_count: {result.hold_count}",
        f"error_count: {result.error_count}",
        f"completed_pop_write_requested: {str(result.completed_pop_write_requested).lower()}",
        f"completed_pop_written_count: {result.completed_pop_written_count}",
        f"items_in_playlist: {result.items_in_playlist}",
        f"last_cycle_status: {result.last_cycle_status}",
        f"reason: {result.reason}",
    ]

    output = "\n".join(lines)

    lower = output.lower()
    for fb in _FORBIDDEN:
        if fb in lower:
            raise ValueError(f"Safe output contains forbidden substring '{fb}'")

    return output
