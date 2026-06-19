"""Safe output formatting for KSO Player.

Only aggregated summaries — never prints full manifest, media bytes,
absolute paths, secrets, tokens, or backend URLs.
"""

from kso_player.playlist import PlayerPlaylist
from kso_player.safety import PlaybackSafetyDecision


def format_playlist_summary(playlist: PlayerPlaylist) -> str:
    """Return a safe aggregated summary of a playlist.

    Never prints: full manifest, media bytes, absolute paths,
    media_path, creatives/, backend URLs, tokens, secrets.
    """
    lines = [
        f"playlist_ready: {str(playlist.ready).lower()}",
        f"status: {playlist.status}",
        f"reason: {playlist.reason}",
        f"items_total: {playlist.items_total}",
        f"items_ready: {playlist.items_ready}",
        f"items_missing: {playlist.items_missing}",
        f"items_failed: {playlist.items_failed}",
    ]
    return "\n".join(lines)


def format_safety_decision(decision: PlaybackSafetyDecision) -> str:
    """Return a safe aggregated summary of a safety decision.

    Never prints: secrets, tokens, paths, backend URLs, stacktrace.
    """
    lines = [
        f"playback_allowed: {str(decision.allowed).lower()}",
        f"action: {decision.action}",
        f"reason: {decision.reason}",
    ]
    return "\n".join(lines)
