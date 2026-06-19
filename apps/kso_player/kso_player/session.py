"""KSO Player Playback Session Core — in-memory item selection.

Pure logic that selects the next media item to play based on:
  - playlist readiness (PlayerPlaylist)
  - safety gate decision (PlaybackSafetyDecision)
  - optional session state (PlaybackSessionState) for sequential progression

No file I/O, no HTTP, no media bytes, no auth, no secret.
Session state is in-memory only — never written to disk.

Invalid session state → fail closed (hold / invalid_state).
"""

from dataclasses import dataclass, field
from typing import Optional

from kso_player.playlist import PlayerPlaylistItem
from kso_player.safety import ACTION_PLAY, ACTION_HOLD, ACTION_STOP

# ══════════════════════════════════════════════════════════════════════
# Reason constants
# ══════════════════════════════════════════════════════════════════════

REASON_SESSION_READY = "ready"
REASON_SESSION_SAFETY_BLOCKED = "safety_blocked"
REASON_SESSION_PLAYLIST_NOT_READY = "playlist_not_ready"
REASON_SESSION_NO_ITEMS = "no_items"
REASON_SESSION_INVALID_STATE = "invalid_state"


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PlaybackSessionState:
    """In-memory session state for sequential playback.

    Tracks which item was played last so the next call can advance.
    Never written to disk. Never contains paths, secrets, or tokens.
    """

    current_index: Optional[int] = None
    last_manifest_item_id: Optional[str] = None
    cycle_count: int = 0


@dataclass
class PlaybackSessionDecision:
    """Result of selecting the next media item.

    Only safe fields — no paths, no secrets, no backend URLs.
    selected_item is None when playback is blocked.
    """

    allowed: bool = False
    action: str = ACTION_STOP
    reason: str = REASON_SESSION_INVALID_STATE
    selected_item: Optional[PlayerPlaylistItem] = None
    next_index: Optional[int] = None
    cycle_count: int = 0


# ══════════════════════════════════════════════════════════════════════
# State validation
# ══════════════════════════════════════════════════════════════════════

# Substrings that make last_manifest_item_id invalid
_FORBIDDEN_IN_STATE = frozenset({
    "token", "secret", "password", "api_key",
    "private_key", "payment_card", "receipt_data",
    "card_number", "pan", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/", "backend_base_url",
    "127.0.0.1", "device_code",
})

_PATH_CHARS = frozenset({"/", "\\", "."})


def _is_valid_state(state, item_count: int) -> bool:
    """Check whether a PlaybackSessionState is valid for the given item count.

    Returns True if state is valid and can be used for progression.
    None current_index is valid (means first run).
    """
    if not isinstance(state, PlaybackSessionState):
        return False

    # ── Validate cycle_count ────────────────────────────────────
    cc = state.cycle_count
    if not isinstance(cc, int) or cc < 0:
        return False

    # ── Validate current_index ──────────────────────────────────
    ci = state.current_index
    if ci is not None:
        if not isinstance(ci, int) or ci < 0 or ci >= item_count:
            return False

    # ── Validate last_manifest_item_id ──────────────────────────
    lmid = state.last_manifest_item_id
    if lmid is not None:
        if not isinstance(lmid, str):
            return False
        lower = lmid.lower()
        for fb in _FORBIDDEN_IN_STATE:
            if fb in lower:
                return False
        # Reject path-like values
        if any(c in lmid for c in _PATH_CHARS if c != "."):
            return False

    return True


# ══════════════════════════════════════════════════════════════════════
# Item selection logic
# ══════════════════════════════════════════════════════════════════════

def select_next_item(
    playlist,
    safety_decision,
    state: Optional[PlaybackSessionState] = None,
) -> PlaybackSessionDecision:
    """Select the next media item for playback.

    Pure logic — no file I/O, no HTTP, no media bytes, no auth, no secret.

    Rules (fail-closed):
        1. If safety_decision.allowed is not True → blocked.
        2. If playlist is not ready → blocked.
        3. If playlist has no items → blocked.
        4. If state is present but invalid → blocked (hold / invalid_state).
        5. Otherwise, select item by order:
           - Without state (None): first item (lowest order).
           - With valid state: item after current_index; wrap around.

    Args:
        playlist: PlayerPlaylist from build_playlist(). Must have .ready and .items.
        safety_decision: PlaybackSafetyDecision from decide_playback_safety().
        state: Optional session state for sequential progression.
               None = first run (starts from first item).
               Invalid state = fail closed (hold / invalid_state).

    Returns:
        PlaybackSessionDecision — always safe, never raises.
    """
    # ── Safety gate check ─────────────────────────────────────────
    if safety_decision is None:
        return PlaybackSessionDecision(
            allowed=False, action=ACTION_STOP,
            reason=REASON_SESSION_SAFETY_BLOCKED,
        )

    try:
        safety_allowed = getattr(safety_decision, "allowed", False)
    except Exception:
        return PlaybackSessionDecision(
            allowed=False, action=ACTION_STOP,
            reason=REASON_SESSION_SAFETY_BLOCKED,
        )

    if not safety_allowed:
        return PlaybackSessionDecision(
            allowed=False, action=ACTION_STOP,
            reason=REASON_SESSION_SAFETY_BLOCKED,
        )

    # ── Playlist check ────────────────────────────────────────────
    if playlist is None:
        return PlaybackSessionDecision(
            allowed=False, action=ACTION_HOLD,
            reason=REASON_SESSION_PLAYLIST_NOT_READY,
        )

    try:
        playlist_ready = getattr(playlist, "ready", False)
        items = getattr(playlist, "items", [])
    except Exception:
        return PlaybackSessionDecision(
            allowed=False, action=ACTION_HOLD,
            reason=REASON_SESSION_PLAYLIST_NOT_READY,
        )

    if not playlist_ready:
        return PlaybackSessionDecision(
            allowed=False, action=ACTION_HOLD,
            reason=REASON_SESSION_PLAYLIST_NOT_READY,
        )

    if not items or len(items) == 0:
        return PlaybackSessionDecision(
            allowed=False, action=ACTION_HOLD,
            reason=REASON_SESSION_NO_ITEMS,
        )

    # ── Sort items by order ───────────────────────────────────────
    try:
        sorted_items = sorted(items, key=lambda it: getattr(it, "order", 0))
    except Exception:
        return PlaybackSessionDecision(
            allowed=False, action=ACTION_HOLD,
            reason=REASON_SESSION_INVALID_STATE,
        )

    n = len(sorted_items)

    # ── Validate session state ────────────────────────────────────
    # None = first run (valid — start from first item).
    # Non-None but invalid = fail closed.
    if state is not None:
        if not _is_valid_state(state, n):
            return PlaybackSessionDecision(
                allowed=False,
                action=ACTION_HOLD,
                reason=REASON_SESSION_INVALID_STATE,
                selected_item=None,
                next_index=None,
                cycle_count=0,
            )

    # ── Determine next index ──────────────────────────────────────
    if state is not None:
        # state is valid PlaybackSessionState
        current = state.current_index
        if current is not None:
            next_index = (current + 1) % n
            cycle_count = state.cycle_count
            if next_index == 0 and current == n - 1:
                cycle_count += 1
        else:
            # current_index is None — first run with state object
            next_index = 0
            cycle_count = 0
    else:
        # state is None — first run without state object
        next_index = 0
        cycle_count = 0

    # ── Select item ───────────────────────────────────────────────
    selected = sorted_items[next_index]

    return PlaybackSessionDecision(
        allowed=True,
        action=ACTION_PLAY,
        reason=REASON_SESSION_READY,
        selected_item=selected,
        next_index=next_index,
        cycle_count=cycle_count,
    )
