"""KSO Player — core skeleton.

Read-only player that builds a playlist from local manifest + media cache.
No backend, no auth, no secret, no HTTP, no UI, no playback.
This is the first safety-focused skeleton for future KSO Player integration.
"""

from kso_player.playlist import (
    PlayerPlaylist,
    PlayerPlaylistItem,
    build_playlist,
    REASON_READY,
    REASON_MANIFEST_MISSING,
    REASON_MANIFEST_INVALID,
    REASON_MEDIA_INCOMPLETE,
    REASON_MEDIA_CORRUPTED,
    REASON_NO_MEDIA_ITEMS,
)
from kso_player.safe_output import (
    format_playlist_summary,
    format_safety_decision,
    format_session_decision,
    format_simulation_result,
)
from kso_player.events import (
    PlaybackEventDraft,
    build_playback_event_draft,
    EVENT_TYPE_WOULD_PLAY,
    EVENT_TYPE_BLOCKED,
    EVENT_TYPE_NOT_READY,
    EVENT_TYPE_ERROR,
    EVENT_STATUS_DRAFT,
)
from kso_player.safety import (
    PlaybackSafetyDecision,
    PlaybackSafetySnapshot,
    decide_playback_safety,
    ALLOWED_STATES,
    ACTION_PLAY,
    ACTION_HOLD,
    ACTION_STOP,
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
)
from kso_player.session import (
    PlaybackSessionDecision,
    PlaybackSessionState,
    select_next_item,
    REASON_SESSION_READY,
    REASON_SESSION_SAFETY_BLOCKED,
    REASON_SESSION_PLAYLIST_NOT_READY,
    REASON_SESSION_NO_ITEMS,
    REASON_SESSION_INVALID_STATE,
)
from kso_player.simulator import (
    PlaybackSimulationResult,
    simulate_playback_step,
    SIM_STATUS_WOULD_PLAY,
    SIM_STATUS_BLOCKED,
    SIM_STATUS_NOT_READY,
    SIM_STATUS_ERROR,
)

__all__ = [
    # Playlist
    "PlayerPlaylist",
    "PlayerPlaylistItem",
    "build_playlist",
    "REASON_READY",
    "REASON_MANIFEST_MISSING",
    "REASON_MANIFEST_INVALID",
    "REASON_MEDIA_INCOMPLETE",
    "REASON_MEDIA_CORRUPTED",
    "REASON_NO_MEDIA_ITEMS",
    # Safety
    "PlaybackSafetySnapshot",
    "PlaybackSafetyDecision",
    "decide_playback_safety",
    "ALLOWED_STATES",
    "ACTION_PLAY",
    "ACTION_HOLD",
    "ACTION_STOP",
    "REASON_SAFETY_READY",
    "REASON_PLAYLIST_NOT_READY",
    "REASON_STATE_UNKNOWN",
    "REASON_TRANSACTION_ACTIVE",
    "REASON_PAYMENT_ACTIVE",
    "REASON_RECEIPT_ACTIVE",
    "REASON_SERVICE_ACTIVE",
    "REASON_ERROR_ACTIVE",
    "REASON_MAINTENANCE_ACTIVE",
    "REASON_OFFLINE",
    "REASON_INVALID_STATE",
    "REASON_MISSING_SNAPSHOT",
    # Session
    "PlaybackSessionState",
    "PlaybackSessionDecision",
    "select_next_item",
    "REASON_SESSION_READY",
    "REASON_SESSION_SAFETY_BLOCKED",
    "REASON_SESSION_PLAYLIST_NOT_READY",
    "REASON_SESSION_NO_ITEMS",
    "REASON_SESSION_INVALID_STATE",
    # Simulator
    "PlaybackSimulationResult",
    "simulate_playback_step",
    "SIM_STATUS_WOULD_PLAY",
    "SIM_STATUS_BLOCKED",
    "SIM_STATUS_NOT_READY",
    "SIM_STATUS_ERROR",
    # Events
    "PlaybackEventDraft",
    "build_playback_event_draft",
    "EVENT_TYPE_WOULD_PLAY",
    "EVENT_TYPE_BLOCKED",
    "EVENT_TYPE_NOT_READY",
    "EVENT_TYPE_ERROR",
    "EVENT_STATUS_DRAFT",
    # Output
    "format_playlist_summary",
    "format_safety_decision",
    "format_session_decision",
    "format_simulation_result",
    "format_playback_event_draft",
]
