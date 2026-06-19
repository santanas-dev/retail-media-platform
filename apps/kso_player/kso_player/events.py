"""KSO Player Playback Event Model — in-memory event draft.

Captures what the player "would have shown" or "did not show" as a
PlaybackEventDraft. This is NOT PoP — no files written, no backend sent.
Pure data model for future PoP integration.

No file I/O, no HTTP, no media bytes, no auth, no secret.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from kso_player.simulator import (
    PlaybackSimulationResult,
    SIM_STATUS_WOULD_PLAY,
    SIM_STATUS_BLOCKED,
    SIM_STATUS_NOT_READY,
    SIM_STATUS_ERROR,
)

# ══════════════════════════════════════════════════════════════════════
# Event type constants
# ══════════════════════════════════════════════════════════════════════

EVENT_TYPE_WOULD_PLAY = "would_play"
EVENT_TYPE_BLOCKED = "blocked"
EVENT_TYPE_NOT_READY = "not_ready"
EVENT_TYPE_ERROR = "error"

EVENT_STATUS_DRAFT = "draft"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PlaybackEventDraft:
    """In-memory draft of a playback event.

    Safe fields only — no paths, no secrets, no media bytes, no backend URLs.
    event_status is always "draft" — NOT written to disk, NOT sent to backend.
    """

    event_type: str = EVENT_TYPE_ERROR
    event_status: str = EVENT_STATUS_DRAFT
    playback_allowed: bool = False
    session_action: str = "stop"
    session_reason: str = "invalid_state"
    selected_order: Optional[int] = None
    selected_content_type: Optional[str] = None
    selected_duration_ms: Optional[int] = None
    started_at: Optional[str] = None       # ISO8601 UTC
    would_end_at: Optional[str] = None     # ISO8601 UTC
    created_at: Optional[str] = None       # ISO8601 UTC


# ══════════════════════════════════════════════════════════════════════
# Event builder
# ══════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_playback_event_draft(
    simulation_result: PlaybackSimulationResult,
    safety_decision=None,
    now: Optional[str] = None,
) -> PlaybackEventDraft:
    """Build a safe in-memory playback event draft from a simulation result.

    Pure logic — no file I/O, no HTTP, no media bytes, no auth, no secret.
    Event is always "draft" — NOT written anywhere.

    Args:
        simulation_result: PlaybackSimulationResult from simulate_playback_step().
        safety_decision: Optional PlaybackSafetyDecision for playback_allowed flag.
        now: Optional ISO8601 timestamp (defaults to current UTC).

    Returns:
        PlaybackEventDraft — always safe, never raises.
    """
    if now is None:
        now = _now_iso()

    # ── Validate input ────────────────────────────────────────────
    if not isinstance(simulation_result, PlaybackSimulationResult):
        return PlaybackEventDraft(
            event_type=EVENT_TYPE_ERROR,
            created_at=now,
        )

    # ── Map simulation_status → event_type ───────────────────────
    sim_status = simulation_result.simulated_status

    if sim_status == SIM_STATUS_WOULD_PLAY:
        event_type = EVENT_TYPE_WOULD_PLAY
    elif sim_status == SIM_STATUS_BLOCKED:
        event_type = EVENT_TYPE_BLOCKED
    elif sim_status == SIM_STATUS_NOT_READY:
        event_type = EVENT_TYPE_NOT_READY
    else:
        event_type = EVENT_TYPE_ERROR

    # ── Determine playback_allowed ────────────────────────────────
    playback_allowed = False
    if safety_decision is not None:
        try:
            playback_allowed = bool(getattr(safety_decision, "allowed", False))
        except Exception:
            pass
    else:
        # Infer from simulation
        playback_allowed = (event_type == EVENT_TYPE_WOULD_PLAY)

    return PlaybackEventDraft(
        event_type=event_type,
        event_status=EVENT_STATUS_DRAFT,
        playback_allowed=playback_allowed,
        session_action=simulation_result.session_action,
        session_reason=simulation_result.session_reason,
        selected_order=simulation_result.selected_order,
        selected_content_type=simulation_result.selected_content_type,
        selected_duration_ms=simulation_result.selected_duration_ms,
        started_at=simulation_result.started_at,
        would_end_at=simulation_result.would_end_at,
        created_at=now,
    )
