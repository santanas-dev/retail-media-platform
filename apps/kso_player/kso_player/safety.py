"""KSO Player Safety Gate — fail-closed core logic.

Determines whether the KSO Player is allowed to show content based on
the current KSO screen state and local playlist readiness.

Pure logic — no file I/O, no HTTP, no auth, no secret, no token.
This is the safety contract: player can ONLY play when KSO is explicitly idle.
All other states → fail closed (stop or hold).
"""

from dataclasses import dataclass, field
from typing import Optional

# ══════════════════════════════════════════════════════════════════════
# KSO Screen States
# ══════════════════════════════════════════════════════════════════════

# The single state where playback is potentially allowed
_IDLE_STATE = "idle"

# All known KSO screen states
ALLOWED_STATES = frozenset({
    "unknown",
    "idle",
    "transaction",
    "payment",
    "receipt",
    "service",
    "error",
    "maintenance",
    "offline",
})

# States that trigger an immediate stop (fail closed)
_STOP_STATES = frozenset({
    "transaction",
    "payment",
    "receipt",
    "service",
    "error",
    "maintenance",
    "offline",
})

# States that trigger hold (not ready to play, but not fatal)
_HOLD_STATES = frozenset({
    "unknown",
})


# ══════════════════════════════════════════════════════════════════════
# Action constants
# ══════════════════════════════════════════════════════════════════════

ACTION_PLAY = "play"
ACTION_HOLD = "hold"
ACTION_STOP = "stop"

# ══════════════════════════════════════════════════════════════════════
# Reason constants
# ══════════════════════════════════════════════════════════════════════

REASON_SAFETY_READY = "ready"
REASON_PLAYLIST_NOT_READY = "playlist_not_ready"
REASON_STATE_UNKNOWN = "state_unknown"
REASON_TRANSACTION_ACTIVE = "transaction_active"
REASON_PAYMENT_ACTIVE = "payment_active"
REASON_RECEIPT_ACTIVE = "receipt_active"
REASON_SERVICE_ACTIVE = "service_active"
REASON_ERROR_ACTIVE = "error_active"
REASON_MAINTENANCE_ACTIVE = "maintenance_active"
REASON_OFFLINE = "offline"
REASON_INVALID_STATE = "invalid_state"
REASON_MISSING_SNAPSHOT = "missing_snapshot"

# State → reason mapping for STOP states
_STATE_TO_REASON: dict[str, str] = {
    "transaction": REASON_TRANSACTION_ACTIVE,
    "payment": REASON_PAYMENT_ACTIVE,
    "receipt": REASON_RECEIPT_ACTIVE,
    "service": REASON_SERVICE_ACTIVE,
    "error": REASON_ERROR_ACTIVE,
    "maintenance": REASON_MAINTENANCE_ACTIVE,
    "offline": REASON_OFFLINE,
}

ALLOWED_SAFETY_REASONS = frozenset({
    REASON_SAFETY_READY,
    REASON_PLAYLIST_NOT_READY,
    REASON_STATE_UNKNOWN,
    REASON_TRANSACTION_ACTIVE,
    REASON_PAYMENT_ACTIVE,
    REASON_RECEIPT_ACTIVE,
    REASON_SERVICE_ACTIVE,
    REASON_ERROR_ACTIVE,
    REASON_MAINTENANCE_ACTIVE,
    REASON_OFFLINE,
    REASON_INVALID_STATE,
    REASON_MISSING_SNAPSHOT,
})


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PlaybackSafetySnapshot:
    """Snapshot of the KSO screen state.

    This is the input to the safety gate. In production this would come
    from the KSO state reader; for now it's a pure data class.

    Only 'idle' state allows potential playback. All other states
    (including unknown/missing) result in fail-closed.
    """

    state: str = "unknown"


@dataclass
class PlaybackSafetyDecision:
    """Fail-closed playback safety decision.

    allowed=True ONLY when: state=idle AND playlist is ready.
    All other combinations → allowed=False.

    Never contains secrets, tokens, paths, or backend URLs.
    """

    allowed: bool = False
    action: str = ACTION_STOP       # "play" | "hold" | "stop"
    reason: str = REASON_INVALID_STATE


# ══════════════════════════════════════════════════════════════════════
# Safety gate logic
# ══════════════════════════════════════════════════════════════════════

def decide_playback_safety(
    snapshot: Optional[PlaybackSafetySnapshot],
    playlist,
) -> PlaybackSafetyDecision:
    """Decide whether playback is allowed based on KSO state and playlist readiness.

    Fail-closed principle: any unexpected input → allowed=False.
    Only 'idle' state + playlist.ready=True → allowed=True, action=play.

    Args:
        snapshot: KSO screen state snapshot. None → fail closed.
        playlist: PlayerPlaylist from build_playlist(). Must have .ready attribute.

    Returns:
        PlaybackSafetyDecision — always safe, never raises, never exposes secrets.
    """
    # ── Missing snapshot → fail closed ────────────────────────────
    if snapshot is None:
        return PlaybackSafetyDecision(
            allowed=False,
            action=ACTION_STOP,
            reason=REASON_MISSING_SNAPSHOT,
        )

    # ── Validate snapshot type ────────────────────────────────────
    if not isinstance(snapshot, PlaybackSafetySnapshot):
        return PlaybackSafetyDecision(
            allowed=False,
            action=ACTION_STOP,
            reason=REASON_INVALID_STATE,
        )

    state = getattr(snapshot, "state", None)

    # ── Validate state ────────────────────────────────────────────
    if not isinstance(state, str) or not state.strip():
        return PlaybackSafetyDecision(
            allowed=False,
            action=ACTION_STOP,
            reason=REASON_INVALID_STATE,
        )

    # Normalize: lowercase, strip whitespace
    state = state.strip().lower()

    # ── Unknown state → hold ──────────────────────────────────────
    if state not in ALLOWED_STATES:
        return PlaybackSafetyDecision(
            allowed=False,
            action=ACTION_STOP,
            reason=REASON_INVALID_STATE,
        )

    # ── Unknown → hold ────────────────────────────────────────────
    if state == "unknown":
        return PlaybackSafetyDecision(
            allowed=False,
            action=ACTION_HOLD,
            reason=REASON_STATE_UNKNOWN,
        )

    # ── Stop states (transaction, payment, receipt, service,
    #    error, maintenance, offline) → stop ───────────────────────
    if state in _STOP_STATES:
        reason = _STATE_TO_REASON.get(state, REASON_INVALID_STATE)
        return PlaybackSafetyDecision(
            allowed=False,
            action=ACTION_STOP,
            reason=reason,
        )

    # ── Idle — must also check playlist readiness ─────────────────
    if state == _IDLE_STATE:
        # Validate playlist
        if playlist is None:
            return PlaybackSafetyDecision(
                allowed=False,
                action=ACTION_HOLD,
                reason=REASON_PLAYLIST_NOT_READY,
            )

        try:
            playlist_ready = getattr(playlist, "ready", False)
        except Exception:
            return PlaybackSafetyDecision(
                allowed=False,
                action=ACTION_HOLD,
                reason=REASON_PLAYLIST_NOT_READY,
            )

        if not playlist_ready:
            return PlaybackSafetyDecision(
                allowed=False,
                action=ACTION_HOLD,
                reason=REASON_PLAYLIST_NOT_READY,
            )

        # ── All conditions met → PLAY ─────────────────────────────
        return PlaybackSafetyDecision(
            allowed=True,
            action=ACTION_PLAY,
            reason=REASON_SAFETY_READY,
        )

    # ── Fallthrough (should never reach here) → fail closed ───────
    return PlaybackSafetyDecision(
        allowed=False,
        action=ACTION_STOP,
        reason=REASON_INVALID_STATE,
    )
