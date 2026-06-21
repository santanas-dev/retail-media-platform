"""KSO Player Runtime Loop Core — multi-cycle ad rotation without Chromium restart.

Pipeline:
  1. (optional) prepare_demo_fixture
  2. Prepare runtime shell workspace once
  3. Write initial bootstrap snapshot
  4. Build guarded Chromium command
  5. (if confirm_launch) launch Chromium once
  6. Build playlist from local manifest
  7. Loop max_cycles times:
     a. Check KSO state gate (idle + fresh?)
     b. If not idle → write hold snapshot, skip PoP
     c. Select next item (round-robin by slot_order)
     d. Write live snapshot for selected item
     e. Wait item's duration_ms via injectable sleep_fn
     f. Re-check state gate
     g. If still idle + confirm_display_completed → write completed PoP
     h. If state changed/stale → no PoP

Chromium is launched at most once — the shell refreshes live.
NO systemd, NO backend, NO sidecar. Completed PoP NEVER automatic.
"""

import json as _json
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
from kso_player.shell_snapshot import (
    SNAPSHOT_MODE_HOLD,
    SNAPSHOT_MODE_RENDER,
    SNAPSHOT_METHOD_SET_HOLD,
    SNAPSHOT_METHOD_SET_RENDER_PLAN,
    SNAPSHOT_SCHEMA_VERSION,
    serialize_kso_shell_snapshot,
)
from kso_player.runtime_snapshot_writer import (
    write_kso_runtime_bootstrap_snapshot,
    _build_js_content,
)
from kso_player.runtime_gate import (
    evaluate_kso_runtime_gate,
    ACTION_PLAY as GATE_PLAY,
)
from kso_player.playlist import build_playlist, PlayerPlaylistItem
from kso_player.simulator import simulate_playback_step, SIM_STATUS_WOULD_PLAY
from kso_player.safety import PlaybackSafetySnapshot, decide_playback_safety
from kso_player.events import build_playback_event_completed
from kso_player.pop_writer import write_pop_event, STATUS_WRITTEN

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_ERROR = "error"

REASON_COMPLETED = "runtime_loop_completed"
REASON_NO_ITEMS = "no_playable_items"
REASON_PREPARE_FAILED = "prepare_failed"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"
REASON_HOLD = "hold"

DURATION_MS_MIN = 1000
DURATION_MS_MAX = 60000

# Forbidden in safe output
_FORBIDDEN_IN_OUTPUT = FORBIDDEN_SUBSTRINGS


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoRuntimeLoopResult:
    """Safe result of a multi-cycle runtime loop.

    NEVER contains absolute paths, file URLs, mediaRef values,
    IDs, raw JSON, exception text, or forbidden substrings.

    Internal fields (_visible_result) use repr=False.
    """

    status: str = STATUS_ERROR
    fixture_ready: bool = False
    shell_prepared: bool = False
    launch_ready: bool = False
    launched: bool = False
    cycles_requested: int = 0
    cycles_completed: int = 0
    rendered_count: int = 0
    hold_count: int = 0
    completed_pop_write_requested: bool = False
    completed_pop_written_count: int = 0
    items_in_playlist: int = 0
    reason: str = REASON_INVALID_ARGS

    _visible_result: Optional[KsoVisibleRuntimeResult] = field(
        default=None, repr=False,
    )

    def __repr__(self) -> str:
        return (
            f"KsoRuntimeLoopResult("
            f"status={self.status!r}, "
            f"fixture_ready={self.fixture_ready}, "
            f"shell_prepared={self.shell_prepared}, "
            f"launch_ready={self.launch_ready}, "
            f"launched={self.launched}, "
            f"cycles_requested={self.cycles_requested}, "
            f"cycles_completed={self.cycles_completed}, "
            f"rendered_count={self.rendered_count}, "
            f"hold_count={self.hold_count}, "
            f"completed_pop_write_requested={self.completed_pop_write_requested}, "
            f"completed_pop_written_count={self.completed_pop_written_count}, "
            f"items_in_playlist={self.items_in_playlist}, "
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

def run_kso_runtime_loop(
    root,
    source_shell_dir,
    runtime_shell_dir,
    chromium_bin: str,
    confirm_launch: bool = False,
    confirm_display_completed: bool = False,
    prepare_demo_fixture: bool = False,
    max_cycles: int = 1,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    process_launcher: Optional[Callable[[List[str]], Optional[object]]] = None,
) -> KsoRuntimeLoopResult:
    """Run a multi-cycle KSO runtime loop with live snapshot rotation.

    Chromium is launched at most once — the shell refreshes via live snapshots.

    Args:
        root: Agent root path.
        source_shell_dir: Immutable shell source directory.
        runtime_shell_dir: Mutable runtime shell directory.
        chromium_bin: Chromium binary path/name.
        confirm_launch: Actually launch Chromium (once).
        confirm_display_completed: Write completed PoP after each successful cycle.
        prepare_demo_fixture: Auto-create demo root.
        max_cycles: Maximum cycles (default 1, for safety).
        stale_seconds: Max state age before stale.
        now: Optional datetime for test time injection.
        sleep_fn: Injectable sleep (test injection).
        process_launcher: Injectable Chromium launcher (test injection).

    Returns:
        KsoRuntimeLoopResult — always safe, never raises.
    """
    if sleep_fn is None:
        sleep_fn = _default_sleep_fn

    # ── Validate args ────────────────────────────────────────────
    if not isinstance(chromium_bin, str) or not chromium_bin.strip():
        return KsoRuntimeLoopResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)
    if stale_seconds <= 0:
        return KsoRuntimeLoopResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)
    if max_cycles < 0:
        return KsoRuntimeLoopResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoRuntimeLoopResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)

    try:
        runtime_dir = Path(runtime_shell_dir)
    except (TypeError, ValueError):
        return KsoRuntimeLoopResult(status=STATUS_ERROR, reason=REASON_INVALID_ARGS)

    # ── Step 1-5: Prepare once + optionally launch Chromium ───────
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
        return KsoRuntimeLoopResult(status=STATUS_ERROR, reason=REASON_INTERNAL_ERROR)

    if visible_result.status == VR_STATUS_ERROR:
        return KsoRuntimeLoopResult(
            status=STATUS_ERROR,
            reason=REASON_PREPARE_FAILED,
            fixture_ready=visible_result.fixture_ready,
            shell_prepared=visible_result.shell_prepared,
            launch_ready=visible_result.launch_ready,
            launched=visible_result.launched,
            cycles_requested=max_cycles,
            _visible_result=visible_result,
        )

    base = KsoRuntimeLoopResult(
        fixture_ready=visible_result.fixture_ready,
        shell_prepared=visible_result.shell_prepared,
        launch_ready=visible_result.launch_ready,
        launched=visible_result.launched,
        cycles_requested=max_cycles,
        completed_pop_write_requested=confirm_display_completed,
        _visible_result=visible_result,
    )

    # ── Step 6: Build playlist ───────────────────────────────────
    try:
        playlist = build_playlist(root)
    except Exception:
        return KsoRuntimeLoopResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
            **{k: getattr(base, k) for k in [
                "fixture_ready", "shell_prepared", "launch_ready",
                "launched", "cycles_requested",
            ]},
        )

    if not playlist.ready or not playlist.items:
        base.status = STATUS_OK
        base.reason = REASON_NO_ITEMS
        base.items_in_playlist = len(playlist.items)
        return base

    items = playlist.items
    base.items_in_playlist = len(items)
    item_count = len(items)

    # ── Step 7-8: Run cycles ────────────────────────────────────
    if max_cycles == 0:
        base.status = STATUS_OK
        base.reason = REASON_COMPLETED
        return base

    for cycle in range(max_cycles):
        # a. Check KSO state gate
        try:
            gate_before = evaluate_kso_runtime_gate(root, stale_seconds, now)
        except Exception:
            base.status = STATUS_ERROR
            base.reason = REASON_INTERNAL_ERROR
            return base

        if gate_before.action != GATE_PLAY:
            # State not idle — write hold snapshot, no PoP
            _write_hold_snapshot(runtime_dir)
            base.hold_count += 1
            base.cycles_completed += 1
            continue

        # c. Select next item (round-robin)
        item_index = cycle % item_count
        item = items[item_index]

        # d. Write render snapshot for this item
        _write_item_snapshot(runtime_dir, item)

        # e. Wait duration (clamped)
        duration_ms = item.duration_ms if item.duration_ms > 0 else DURATION_MS_MIN
        duration_ms = min(max(duration_ms, DURATION_MS_MIN), DURATION_MS_MAX)
        try:
            sleep_fn(duration_ms / 1000.0)
        except Exception:
            base.status = STATUS_ERROR
            base.reason = REASON_INTERNAL_ERROR
            return base

        # f. Re-check state
        try:
            gate_after = evaluate_kso_runtime_gate(root, stale_seconds, now)
        except Exception:
            # Gate error → hold, no PoP
            base.cycles_completed += 1
            base.rendered_count += 1
            continue

        # g. If still idle + confirm → write completed PoP
        if gate_after.action == GATE_PLAY and confirm_display_completed:
            _write_completed_pop_for_item(root, item, gate_after.state)
            base.completed_pop_written_count += 1
        # h. State changed → no PoP (but cycle counted as rendered)

        base.cycles_completed += 1
        base.rendered_count += 1

    base.status = STATUS_OK
    base.reason = REASON_COMPLETED
    return base


# ══════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════

def _write_hold_snapshot(runtime_dir: Path) -> None:
    """Write a hold mode bootstrap_snapshot.js."""
    js = (
        '"use strict";\n'
        'window.KSO_PLAYER_BOOTSTRAP_SNAPSHOT = '
        '{"schemaVersion":1,"mode":"hold","method":"setHold",'
        '"payload":{"reason":"hold"}};\n'
    )
    _write_snapshot_atomic(js, runtime_dir)


def _write_item_snapshot(runtime_dir: Path, item: PlayerPlaylistItem) -> None:
    """Write a render mode bootstrap_snapshot.js for the given playlist item."""
    media_type = _map_content_type(item.content_type)
    duration_bucket = _map_duration_bucket(item.duration_ms)

    payload = {
        "mediaType": media_type,
        "durationBucket": duration_bucket,
    }

    # Include mediaRef from the item (safe alias)
    media_ref = item.media_ref or ""
    if not media_ref:
        # Legacy: build from filename
        media_ref = f"media/current/{item.filename}" if item.filename else ""

    if media_ref:
        payload["mediaRef"] = media_ref

    obj = {
        "schemaVersion": 1,
        "mode": "render",
        "method": "setRenderPlan",
        "payload": payload,
    }

    snapshot_json = _json.dumps(obj, sort_keys=True, separators=(",", ":"))
    js = _build_js_content(snapshot_json)
    _write_snapshot_atomic(js, runtime_dir)


def _write_snapshot_atomic(js_content: str, runtime_dir: Path) -> None:
    """Write bootstrap_snapshot.js atomically to runtime_dir."""
    import tempfile
    import os

    runtime_dir.mkdir(parents=True, exist_ok=True)
    dst = runtime_dir / "bootstrap_snapshot.js"

    try:
        fd, tmp = tempfile.mkstemp(
            dir=str(runtime_dir),
            prefix=".bootstrap_snapshot.js.",
            suffix=".tmp",
        )
        try:
            os.write(fd, js_content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, str(dst))
    except OSError:
        pass  # fail-silent — shell will keep previous snapshot


def _write_completed_pop_for_item(
    root: Path, item: PlayerPlaylistItem, safety_state: str,
) -> None:
    """Write a completed PoP event for the given item."""
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
        pass  # fail-silent


def _map_content_type(content_type: str) -> str:
    """Map MIME type to safe media type string for shell."""
    if not content_type:
        return "image"
    ct = content_type.lower()
    if ct.startswith("video/"):
        return "video"
    return "image"


def _map_duration_bucket(duration_ms: int) -> str:
    """Map duration in ms to a duration bucket."""
    if duration_ms < 10000:
        return "short"
    if duration_ms <= 60000:
        return "medium"
    return "long"


# ══════════════════════════════════════════════════════════════════════
# Safe output
# ══════════════════════════════════════════════════════════════════════

def format_kso_runtime_loop_result(result: KsoRuntimeLoopResult) -> str:
    """Format result as a safe human-readable string.

    NEVER contains absolute paths, file URLs, mediaRef values,
    IDs, raw JSON, exception text, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"fixture_ready: {str(result.fixture_ready).lower()}",
        f"shell_prepared: {str(result.shell_prepared).lower()}",
        f"launch_ready: {str(result.launch_ready).lower()}",
        f"launched: {str(result.launched).lower()}",
        f"cycles_requested: {result.cycles_requested}",
        f"cycles_completed: {result.cycles_completed}",
        f"rendered_count: {result.rendered_count}",
        f"hold_count: {result.hold_count}",
        f"completed_pop_write_requested: {str(result.completed_pop_write_requested).lower()}",
        f"completed_pop_written_count: {result.completed_pop_written_count}",
        f"items_in_playlist: {result.items_in_playlist}",
        f"reason: {result.reason}",
    ]

    output = "\n".join(lines)

    lower = output.lower()
    for fb in _FORBIDDEN_IN_OUTPUT:
        if fb in lower:
            raise ValueError(f"Safe output contains forbidden substring '{fb}'")

    return output
