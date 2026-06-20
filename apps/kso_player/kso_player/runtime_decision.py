"""KSO Player Local Playback Decision Core — full play/hold pipeline.

Orchestrates the playback decision chain:
1. Runtime gate: read kso_state.json → idle + fresh?
2. Local content: manifest/playlist/media readiness
3. Session/safety: select next playable item

Returns a safe aggregate KsoPlaybackRuntimeDecisionResult.
NO Chromium, NO UI, NO HTTP, NO PoP write (flag only), NO backend.
Player NEVER writes kso_state.json.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from kso_player.runtime_gate import (
    evaluate_kso_runtime_gate,
    KsoRuntimeGateResult,
    ACTION_PLAY as GATE_PLAY,
    ACTION_HOLD as GATE_HOLD,
    ALLOWED_STATES,
    FORBIDDEN_SUBSTRINGS,
)
from kso_player.playlist import build_playlist
from kso_player.safety import (
    PlaybackSafetySnapshot,
    decide_playback_safety,
    ACTION_PLAY as SAFETY_PLAY,
)
from kso_player.session import (
    select_next_item,
    PlaybackSessionDecision,
    ACTION_PLAY as SESSION_PLAY,
    ACTION_HOLD as SESSION_HOLD,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

ACTION_PLAY = "play"
ACTION_HOLD = "hold"

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

# ── Reasons ─────────────────────────────────────────────────────────

REASON_READY_TO_PLAY = "ready_to_play"
REASON_STATE_GATE_HOLD = "state_gate_hold"
REASON_LOCAL_CONTENT_NOT_READY = "local_content_not_ready"
REASON_SESSION_OR_SAFETY_HOLD = "session_or_safety_hold"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoPlaybackRuntimeDecisionResult:
    """Safe result of the full playback decision chain.

    Never contains absolute paths, file names, manifest item IDs,
    campaign IDs, creative IDs, schedule item IDs, media paths,
    media file names, sha256, source values, timestamps,
    exception text, or forbidden substrings.
    """

    status: str = STATUS_ERROR
    play_allowed: bool = False
    action: str = ACTION_HOLD
    reason: str = REASON_INVALID_ARGS
    gate_action: str = ACTION_HOLD
    state: str = "unknown"
    content_ready: bool = False
    selected_present: bool = False
    pop_event_should_be_written: bool = False

    def __repr__(self) -> str:
        return (
            f"KsoPlaybackRuntimeDecisionResult("
            f"status={self.status!r}, "
            f"play_allowed={self.play_allowed}, "
            f"action={self.action!r}, "
            f"reason={self.reason!r}, "
            f"gate_action={self.gate_action!r}, "
            f"state={self.state!r}, "
            f"content_ready={self.content_ready}, "
            f"selected_present={self.selected_present}, "
            f"pop_event_should_be_written={self.pop_event_should_be_written})"
        )


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def evaluate_kso_playback_runtime_decision(
    root,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
) -> KsoPlaybackRuntimeDecisionResult:
    """Evaluate whether the KSO player should play or hold.

    Decision chain:
    1. Runtime gate: read kso_state.json → idle + fresh?
       If gate blocks → hold immediately.
    2. Local content: build_playlist() → manifest + media ready?
       If content not ready → hold.
    3. Session/safety: decide_playback_safety + select_next_item.
       If a playable item is selected → play.

    Args:
        root: Agent root path (str or Path).
        stale_seconds: Max state age before stale (default 30s).
        now: Optional datetime for test time injection.

    Returns:
        KsoPlaybackRuntimeDecisionResult — safe aggregate, never raises.
    """
    # ── Validate args ────────────────────────────────────────────
    if stale_seconds <= 0:
        return KsoPlaybackRuntimeDecisionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoPlaybackRuntimeDecisionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Step 1: Runtime gate ─────────────────────────────────────
    try:
        gate_result = evaluate_kso_runtime_gate(root, stale_seconds, now)
    except Exception:
        return KsoPlaybackRuntimeDecisionResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
        )

    state = gate_result.state
    gate_action = gate_result.action

    if not gate_result.play_allowed:
        return KsoPlaybackRuntimeDecisionResult(
            status=gate_result.status,
            action=ACTION_HOLD,
            reason=REASON_STATE_GATE_HOLD,
            gate_action=gate_action,
            state=state,
        )

    # ── Step 2: Local content readiness ──────────────────────────
    try:
        playlist = build_playlist(root)
    except Exception:
        return KsoPlaybackRuntimeDecisionResult(
            status=STATUS_ERROR,
            action=ACTION_HOLD,
            reason=REASON_LOCAL_CONTENT_NOT_READY,
            gate_action=gate_action,
            state=state,
        )

    if not playlist.ready or playlist.items_ready == 0:
        return KsoPlaybackRuntimeDecisionResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            reason=REASON_LOCAL_CONTENT_NOT_READY,
            gate_action=gate_action,
            state=state,
            content_ready=False,
        )

    # ── Step 3: Session / safety ─────────────────────────────────
    try:
        snapshot = PlaybackSafetySnapshot(state=state)
        safety_decision = decide_playback_safety(snapshot, playlist)
    except Exception:
        return KsoPlaybackRuntimeDecisionResult(
            status=STATUS_ERROR,
            action=ACTION_HOLD,
            reason=REASON_SESSION_OR_SAFETY_HOLD,
            gate_action=gate_action,
            state=state,
            content_ready=True,
        )

    if not safety_decision.allowed:
        return KsoPlaybackRuntimeDecisionResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            reason=REASON_SESSION_OR_SAFETY_HOLD,
            gate_action=gate_action,
            state=state,
            content_ready=True,
        )

    try:
        session_decision = select_next_item(
            playlist, safety_decision, state=None)
    except Exception:
        return KsoPlaybackRuntimeDecisionResult(
            status=STATUS_ERROR,
            action=ACTION_HOLD,
            reason=REASON_SESSION_OR_SAFETY_HOLD,
            gate_action=gate_action,
            state=state,
            content_ready=True,
        )

    if not session_decision.allowed or session_decision.selected_item is None:
        return KsoPlaybackRuntimeDecisionResult(
            status=STATUS_WARNING,
            action=ACTION_HOLD,
            reason=REASON_SESSION_OR_SAFETY_HOLD,
            gate_action=gate_action,
            state=state,
            content_ready=True,
            selected_present=False,
        )

    # ── READY TO PLAY ────────────────────────────────────────────
    return KsoPlaybackRuntimeDecisionResult(
        status=STATUS_OK,
        play_allowed=True,
        action=ACTION_PLAY,
        reason=REASON_READY_TO_PLAY,
        gate_action=gate_action,
        state=state,
        content_ready=True,
        selected_present=True,
        pop_event_should_be_written=True,
    )


def format_kso_playback_runtime_decision_result(
    result: KsoPlaybackRuntimeDecisionResult,
) -> str:
    """Format a KsoPlaybackRuntimeDecisionResult as a safe human-readable string.

    Never contains paths, IDs, secrets, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"play_allowed: {str(result.play_allowed).lower()}",
        f"action: {result.action}",
        f"reason: {result.reason}",
        f"gate_action: {result.gate_action}",
        f"state: {result.state}",
        f"content_ready: {str(result.content_ready).lower()}",
        f"selected_present: {str(result.selected_present).lower()}",
        f"pop_event_should_be_written: "
        f"{str(result.pop_event_should_be_written).lower()}",
    ]
    return "\n".join(lines)
