"""KSO Player Display Cycle — single render decision + optional PoP write.

Core contract for the player's display loop:
  idle state + safe manifest + ready media → render item selected
  → simulated display cycle completed → [optional] write local PoP event.

PoP is NOT written by default. Caller must pass confirm_pop_write=True.
This is a core contract, NOT final production PoP proof — the future
Chromium runtime loop must call this only after display duration elapsed.

NO Chromium, NO backend, NO sidecar, NO systemd, NO PoP ingest.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from kso_player.runtime_gate import (
    evaluate_kso_runtime_gate,
    ACTION_PLAY as GATE_PLAY,
)
from kso_player.render_plan import (
    build_kso_render_plan,
    RENDER_ACTION_RENDER,
    RENDER_ACTION_HOLD,
)
from kso_player.simulator import (
    simulate_playback_step,
    PlaybackSimulationResult,
    SIM_STATUS_WOULD_PLAY,
)
from kso_player.events import (
    build_playback_event_draft,
    PlaybackEventDraft,
)
from kso_player.safety import PlaybackSafetySnapshot, decide_playback_safety
from kso_player.playlist import build_playlist
from kso_player.pop_writer import (
    write_pop_event,
    PopWriteResult,
    STATUS_WRITTEN,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_HOLD = "hold"

REASON_RENDER_READY = "render_ready"
REASON_POP_WRITTEN = "pop_written"
REASON_NO_POP_CONFIRM = "render_ready_no_pop_confirm"
REASON_DECISION_HOLD = "decision_hold"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"

# ══════════════════════════════════════════════════════════════════════
# Result
# ══════════════════════════════════════════════════════════════════════


@dataclass
class KsoDisplayCycleResult:
    """Safe result of one display cycle.

    NEVER contains: paths, filenames, mediaRef values, raw JSON,
    raw manifests, IDs, hashes, backend URLs, secrets, stacktrace.
    """

    status: str = STATUS_ERROR
    render_ready: bool = False
    render_action: str = RENDER_ACTION_HOLD
    pop_write_requested: bool = False
    pop_written: bool = False
    reason: str = REASON_INVALID_ARGS

    # Internal — never exposed in repr/format
    _pop_write_result: Optional[PopWriteResult] = None

    def __repr__(self) -> str:
        return (
            f"KsoDisplayCycleResult("
            f"status={self.status!r}, "
            f"render_ready={self.render_ready}, "
            f"render_action={self.render_action!r}, "
            f"pop_write_requested={self.pop_write_requested}, "
            f"pop_written={self.pop_written}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Core API
# ══════════════════════════════════════════════════════════════════════


def run_kso_display_cycle_once(
    root,
    now: Optional[datetime] = None,
    stale_seconds: int = 30,
    confirm_pop_write: bool = False,
) -> KsoDisplayCycleResult:
    """Run one KSO display cycle: gate → render decision → [optional] PoP write.

    Steps:
      1. Render plan (wraps gate + playlist + safety + session)
      2. If render → simulate playback step → build event draft
      3. If confirm_pop_write → write PoP event via pop_writer
      4. Return safe aggregate result

    PoP is NEVER written unless confirm_pop_write=True.
    This is core contract — not final production display proof.

    Args:
        root: Agent root path (str or Path).
        now: Optional datetime for test time injection.
        stale_seconds: Max state age before stale (default 30s).
        confirm_pop_write: If True, write PoP event to local JSONL.

    Returns:
        KsoDisplayCycleResult — safe aggregate, never raises.
    """
    # ── Validate args ────────────────────────────────────────────
    if stale_seconds <= 0:
        return KsoDisplayCycleResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoDisplayCycleResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Step 1: Render plan ──────────────────────────────────────
    try:
        plan = build_kso_render_plan(root, stale_seconds, now)
    except Exception:
        return KsoDisplayCycleResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
        )

    if plan.render_action != RENDER_ACTION_RENDER:
        return KsoDisplayCycleResult(
            status=plan.status,
            reason=REASON_DECISION_HOLD,
            render_action=plan.render_action,
        )

    # ── Render is ready ─────────────────────────────────────────
    if not confirm_pop_write:
        return KsoDisplayCycleResult(
            status=STATUS_OK,
            render_ready=True,
            render_action=RENDER_ACTION_RENDER,
            reason=REASON_NO_POP_CONFIRM,
        )

    # ── Step 2: Gate (get state for PoP) ──────────────────────
    try:
        gate = evaluate_kso_runtime_gate(root, stale_seconds, now)
        safety_state = gate.state
    except Exception:
        return KsoDisplayCycleResult(
            status=STATUS_ERROR,
            render_ready=True,
            render_action=RENDER_ACTION_RENDER,
            pop_write_requested=True,
            reason=REASON_INTERNAL_ERROR,
        )

    # ── Step 3: Simulate + build event draft ────────────────────
    try:
        playlist = build_playlist(root)
        snapshot = PlaybackSafetySnapshot(state=safety_state)
        safety_decision = decide_playback_safety(snapshot, playlist)

        sim_result = simulate_playback_step(
            playlist, safety_decision, session_state=None,
        )
    except Exception:
        return KsoDisplayCycleResult(
            status=STATUS_ERROR,
            render_ready=True,
            render_action=RENDER_ACTION_RENDER,
            pop_write_requested=True,
            reason=REASON_INTERNAL_ERROR,
        )

    try:
        event_draft = build_playback_event_draft(sim_result)
    except Exception:
        return KsoDisplayCycleResult(
            status=STATUS_ERROR,
            render_ready=True,
            render_action=RENDER_ACTION_RENDER,
            pop_write_requested=True,
            reason=REASON_INTERNAL_ERROR,
        )

    # ── Step 4: Write PoP ───────────────────────────────────────

    try:
        pop_result = write_pop_event(root, event_draft, safety_state)
    except Exception:
        return KsoDisplayCycleResult(
            status=STATUS_ERROR,
            render_ready=True,
            render_action=RENDER_ACTION_RENDER,
            pop_write_requested=True,
            reason=REASON_INTERNAL_ERROR,
        )

    if pop_result.status == STATUS_WRITTEN:
        return KsoDisplayCycleResult(
            status=STATUS_OK,
            render_ready=True,
            render_action=RENDER_ACTION_RENDER,
            pop_write_requested=True,
            pop_written=True,
            reason=REASON_POP_WRITTEN,
            _pop_write_result=pop_result,
        )

    return KsoDisplayCycleResult(
        status=STATUS_WARNING,
        render_ready=True,
        render_action=RENDER_ACTION_RENDER,
        pop_write_requested=True,
        pop_written=False,
        reason=pop_result.reason,
        _pop_write_result=pop_result,
    )


# ══════════════════════════════════════════════════════════════════════
# Formatter
# ══════════════════════════════════════════════════════════════════════


def format_kso_display_cycle_result(result: KsoDisplayCycleResult) -> str:
    """Format display cycle result as safe human-readable string.

    NEVER contains: paths, filenames, mediaRef values, raw JSON,
    IDs, hashes, backend URLs, secrets, stacktrace.
    """
    lines = [
        f"status: {result.status}",
        f"render_ready: {str(result.render_ready).lower()}",
        f"render_action: {result.render_action}",
        f"pop_write_requested: {str(result.pop_write_requested).lower()}",
        f"pop_written: {str(result.pop_written).lower()}",
        f"reason: {result.reason}",
    ]
    return "\n".join(lines)
