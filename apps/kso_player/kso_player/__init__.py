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
from kso_player.safe_output import format_playlist_summary

__all__ = [
    "PlayerPlaylist",
    "PlayerPlaylistItem",
    "build_playlist",
    "format_playlist_summary",
    "REASON_READY",
    "REASON_MANIFEST_MISSING",
    "REASON_MANIFEST_INVALID",
    "REASON_MEDIA_INCOMPLETE",
    "REASON_MEDIA_CORRUPTED",
    "REASON_NO_MEDIA_ITEMS",
]
