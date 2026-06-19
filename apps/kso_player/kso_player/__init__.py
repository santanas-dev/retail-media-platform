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
    # Output
    "format_playlist_summary",
    "format_safety_decision",
    "format_session_decision",
]
