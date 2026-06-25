"""KSO Player Playback Simulator Core — simulated playback step.

Wraps the full pipeline: playlist → safety → session → simulated result.
No actual media playback, no sleep, no file writes, no HTTP, no PoP.
Pure logic that models what WOULD happen if playback were performed.

Timestamps are ISO8601 UTC. No real delay — duration is calculated.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from kso_player.session import (
    PlaybackSessionState,
    PlaybackSessionDecision,
    select_next_item,
    REASON_SESSION_READY,
    REASON_SESSION_SAFETY_BLOCKED,
    REASON_SESSION_PLAYLIST_NOT_READY,
    REASON_SESSION_NO_ITEMS,
    REASON_SESSION_INVALID_STATE,
)

# ══════════════════════════════════════════════════════════════════════
# Simulation status constants
# ══════════════════════════════════════════════════════════════════════

SIM_STATUS_WOULD_PLAY = "would_play"
SIM_STATUS_BLOCKED = "blocked"
SIM_STATUS_NOT_READY = "not_ready"
SIM_STATUS_ERROR = "error"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PlaybackSimulationResult:
    """Result of a simulated playback step.

    Safe fields only — no paths, no secrets, no media bytes, no backend URLs.
    started_at / would_end_at are ISO8601 UTC timestamps (calculated, no real delay).
    """

    simulated_status: str = SIM_STATUS_ERROR
    session_action: str = "stop"
    session_reason: str = REASON_SESSION_INVALID_STATE
    selected_order: Optional[int] = None
    selected_content_type: Optional[str] = None
    selected_duration_ms: Optional[int] = None
    started_at: Optional[str] = None      # ISO8601 UTC
    would_end_at: Optional[str] = None    # ISO8601 UTC
    next_index: Optional[int] = None
    cycle_count: int = 0


# ══════════════════════════════════════════════════════════════════════
# Simulation logic
# ══════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_add_ms(iso: str, duration_ms: int) -> str:
    """Add duration_ms to an ISO8601 timestamp."""
    try:
        from kso_player.timestamp_utils import parse_iso_utc
        dt = parse_iso_utc(iso)
        if dt is None:
            return iso
    except (ValueError, TypeError):
        return iso
    return (dt + timedelta(milliseconds=duration_ms)).isoformat()


def simulate_playback_step(
    playlist,
    safety_decision,
    session_state: Optional[PlaybackSessionState] = None,
    now: Optional[str] = None,
) -> PlaybackSimulationResult:
    """Simulate one playback step.

    Pure logic — no media playback, no sleep, no file I/O, no HTTP.

    Pipeline:
        1. select_next_item(playlist, safety_decision, session_state)
        2. If session decision is not 'play' → blocked/not_ready/error
        3. If 'play' → would_play with calculated timestamps

    Args:
        playlist: PlayerPlaylist from build_playlist().
        safety_decision: PlaybackSafetyDecision from decide_playback_safety().
        session_state: Optional session state for progression.
        now: Optional ISO8601 timestamp (defaults to current UTC).

    Returns:
        PlaybackSimulationResult — always safe, never raises.
    """
    if now is None:
        now = _now_iso()

    # ── Step 1: Session decision ──────────────────────────────────
    session = select_next_item(playlist, safety_decision, session_state)

    # ── Step 2: Determine simulated_status ────────────────────────
    if session.action == "play":
        item = session.selected_item

        # Calculate would_end_at
        duration_ms = getattr(item, "duration_ms", 0) if item is not None else 0
        started_at = now
        would_end_at = _iso_add_ms(started_at, duration_ms) if duration_ms > 0 else started_at

        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_WOULD_PLAY,
            session_action=session.action,
            session_reason=session.reason,
            selected_order=getattr(item, "order", None) if item else None,
            selected_content_type=getattr(item, "content_type", None) if item else None,
            selected_duration_ms=duration_ms if item else None,
            started_at=started_at,
            would_end_at=would_end_at,
            next_index=session.next_index,
            cycle_count=session.cycle_count,
        )
    elif session.reason in (REASON_SESSION_SAFETY_BLOCKED, REASON_SESSION_NO_ITEMS,
                             REASON_SESSION_INVALID_STATE):
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_BLOCKED,
            session_action=session.action,
            session_reason=session.reason,
            next_index=session.next_index,
            cycle_count=session.cycle_count,
        )
    elif session.reason == REASON_SESSION_PLAYLIST_NOT_READY:
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_NOT_READY,
            session_action=session.action,
            session_reason=session.reason,
            next_index=session.next_index,
            cycle_count=session.cycle_count,
        )
    else:
        result = PlaybackSimulationResult(
            simulated_status=SIM_STATUS_ERROR,
            session_action=session.action,
            session_reason=session.reason,
            next_index=session.next_index,
            cycle_count=session.cycle_count,
        )

    return result
