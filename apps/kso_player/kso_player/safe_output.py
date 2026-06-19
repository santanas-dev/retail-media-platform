"""Safe output formatting for KSO Player.

Only aggregated summaries — never prints full manifest, media bytes,
absolute paths, secrets, tokens, or backend URLs.
"""

from kso_player.playlist import PlayerPlaylist
from kso_player.safety import PlaybackSafetyDecision
from kso_player.session import PlaybackSessionDecision
from kso_player.simulator import PlaybackSimulationResult
from kso_player.events import PlaybackEventDraft


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


def format_session_decision(decision: PlaybackSessionDecision) -> str:
    """Return a safe aggregated summary of a session decision.

    Never prints: filename, manifest_item_id, sha256, absolute paths,
    media bytes, secrets, tokens.
    """
    lines = [
        f"session_action: {decision.action}",
        f"session_reason: {decision.reason}",
    ]

    if decision.selected_item is not None:
        item = decision.selected_item
        lines.append(f"selected_order: {item.order}")
        lines.append(f"selected_content_type: {item.content_type}")
        lines.append(f"selected_duration_ms: {item.duration_ms}")

    return "\n".join(lines)


def format_simulation_result(result: PlaybackSimulationResult) -> str:
    """Return a safe aggregated summary of a simulation result.

    Never prints: filename, manifest_item_id, sha256, absolute paths,
    media bytes, secrets, tokens.
    """
    lines = [
        f"simulation_status: {result.simulated_status}",
        f"session_action: {result.session_action}",
        f"session_reason: {result.session_reason}",
    ]

    if result.selected_order is not None:
        lines.append(f"selected_order: {result.selected_order}")
    if result.selected_content_type is not None:
        lines.append(f"selected_content_type: {result.selected_content_type}")
    if result.selected_duration_ms is not None:
        lines.append(f"selected_duration_ms: {result.selected_duration_ms}")

    return "\n".join(lines)


def format_playback_event_draft(event: PlaybackEventDraft) -> str:
    """Return a safe aggregated summary of a playback event draft.

    Never prints: filename, manifest_item_id, sha256, absolute paths,
    media bytes, full manifest, secrets, tokens, backend URLs,
    customer/payment/card/receipt details.
    """
    lines = [
        f"event_type: {event.event_type}",
        f"event_status: {event.event_status}",
        f"playback_allowed: {str(event.playback_allowed).lower()}",
        f"session_action: {event.session_action}",
        f"session_reason: {event.session_reason}",
    ]

    if event.selected_order is not None:
        lines.append(f"selected_order: {event.selected_order}")
    if event.selected_content_type is not None:
        lines.append(f"selected_content_type: {event.selected_content_type}")
    if event.selected_duration_ms is not None:
        lines.append(f"selected_duration_ms: {event.selected_duration_ms}")

    return "\n".join(lines)
