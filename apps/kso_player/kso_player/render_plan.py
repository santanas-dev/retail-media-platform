"""KSO Player Local Render Plan Core — safe render/hold plan builder.

Builds on top of the runtime decision chain to produce a safe render plan:
1. Runtime decision: state gate → content → session/safety
2. If play allowed → extract item details → media_type → duration_bucket
3. Return render_action=render or hold with safe aggregates

Internal fields (repr=False): _selected_item, _media_type, _duration_seconds.
External safe fields only: render_action, media_type, duration_bucket.

NO Chromium, NO UI, NO HTTP, NO PoP write, NO backend.
Player NEVER writes kso_state.json.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from kso_player.runtime_decision import (
    evaluate_kso_playback_runtime_decision,
    KsoPlaybackRuntimeDecisionResult,
    ACTION_PLAY as DECISION_PLAY,
    FORBIDDEN_SUBSTRINGS,
)
from kso_player.playlist import build_playlist, PlayerPlaylistItem
from kso_player.safety import (
    PlaybackSafetySnapshot,
    decide_playback_safety,
)
from kso_player.session import (
    select_next_item,
    PlaybackSessionDecision,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

RENDER_ACTION_RENDER = "render"
RENDER_ACTION_HOLD = "hold"

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

# ── Media types ─────────────────────────────────────────────────────

MEDIA_IMAGE = "image"
MEDIA_VIDEO = "video"
MEDIA_UNKNOWN = "unknown"

# ── Duration buckets ────────────────────────────────────────────────

DURATION_SHORT = "short"      # < 10s
DURATION_MEDIUM = "medium"    # 10–60s
DURATION_LONG = "long"        # > 60s
DURATION_UNKNOWN = "unknown"

# ── Reasons ─────────────────────────────────────────────────────────

REASON_READY_TO_RENDER = "ready_to_render"
REASON_DECISION_HOLD = "decision_hold"
REASON_UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
REASON_NO_SELECTED_ITEM = "no_selected_item"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoRenderPlanResult:
    """Safe render plan for the future Chromium-based renderer.

    External safe fields only. Internal fields with repr=False are
    never exposed in repr, format, stdout, stderr, or errors.
    """

    status: str = STATUS_ERROR
    render_action: str = RENDER_ACTION_HOLD
    play_allowed: bool = False
    reason: str = REASON_INVALID_ARGS
    decision_reason: str = "unknown"
    selected_present: bool = False
    media_type: str = MEDIA_UNKNOWN
    duration_bucket: str = DURATION_UNKNOWN
    pop_event_should_be_written: bool = False

    # Internal fields — NEVER exposed in safe output
    _selected_item: Optional[PlayerPlaylistItem] = field(
        default=None, repr=False)
    _duration_seconds: float = field(default=0.0, repr=False)

    def __repr__(self) -> str:
        return (
            f"KsoRenderPlanResult("
            f"status={self.status!r}, "
            f"render_action={self.render_action!r}, "
            f"play_allowed={self.play_allowed}, "
            f"reason={self.reason!r}, "
            f"decision_reason={self.decision_reason!r}, "
            f"selected_present={self.selected_present}, "
            f"media_type={self.media_type!r}, "
            f"duration_bucket={self.duration_bucket!r}, "
            f"pop_event_should_be_written={self.pop_event_should_be_written})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _classify_media_type(content_type: str) -> str:
    """Map MIME content_type to media_type bucket."""
    if not isinstance(content_type, str):
        return MEDIA_UNKNOWN
    ct = content_type.strip().lower()
    if ct.startswith("image/"):
        return MEDIA_IMAGE
    if ct.startswith("video/"):
        return MEDIA_VIDEO
    return MEDIA_UNKNOWN


def _classify_duration(duration_ms: int) -> str:
    """Map duration_ms to duration bucket."""
    if not isinstance(duration_ms, int) or duration_ms < 0:
        return DURATION_UNKNOWN
    if duration_ms < 10000:
        return DURATION_SHORT
    if duration_ms <= 60000:
        return DURATION_MEDIUM
    return DURATION_LONG


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def build_kso_render_plan(
    root,
    stale_seconds: int = 30,
    now: Optional[datetime] = None,
) -> KsoRenderPlanResult:
    """Build a safe render plan for the KSO player.

    Pipeline:
    1. Runtime decision → state gate + content + session/safety
    2. If play allowed → extract item → classify media_type + duration
    3. Return render_action=render or hold

    Args:
        root: Agent root path (str or Path).
        stale_seconds: Max state age before stale (default 30s).
        now: Optional datetime for test time injection.

    Returns:
        KsoRenderPlanResult — safe aggregate, never raises.
    """
    # ── Validate args ────────────────────────────────────────────
    if stale_seconds <= 0:
        return KsoRenderPlanResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoRenderPlanResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Step 1: Runtime decision ─────────────────────────────────
    try:
        decision = evaluate_kso_playback_runtime_decision(
            root, stale_seconds, now)
    except Exception:
        return KsoRenderPlanResult(
            status=STATUS_ERROR,
            reason=REASON_INTERNAL_ERROR,
        )

    decision_reason = decision.reason

    if not decision.play_allowed:
        return KsoRenderPlanResult(
            status=decision.status,
            render_action=RENDER_ACTION_HOLD,
            reason=REASON_DECISION_HOLD,
            decision_reason=decision_reason,
        )

    # ── Step 2: Get selected item ────────────────────────────────
    try:
        playlist = build_playlist(root)
        snapshot = PlaybackSafetySnapshot(state=decision.state)
        safety_decision = decide_playback_safety(snapshot, playlist)
        session_result = select_next_item(playlist, safety_decision)
    except Exception:
        return KsoRenderPlanResult(
            status=STATUS_ERROR,
            render_action=RENDER_ACTION_HOLD,
            reason=REASON_INTERNAL_ERROR,
            decision_reason=decision_reason,
        )

    selected_item = session_result.selected_item
    if selected_item is None:
        return KsoRenderPlanResult(
            status=STATUS_WARNING,
            render_action=RENDER_ACTION_HOLD,
            reason=REASON_NO_SELECTED_ITEM,
            decision_reason=decision_reason,
        )

    # ── Step 3: Classify media ───────────────────────────────────
    content_type = getattr(selected_item, "content_type", "")
    media_type = _classify_media_type(content_type)

    if media_type == MEDIA_UNKNOWN:
        return KsoRenderPlanResult(
            status=STATUS_WARNING,
            render_action=RENDER_ACTION_HOLD,
            reason=REASON_UNSUPPORTED_MEDIA_TYPE,
            decision_reason=decision_reason,
            selected_present=True,
            media_type=MEDIA_UNKNOWN,
            _selected_item=selected_item,
        )

    duration_ms = getattr(selected_item, "duration_ms", 0)
    duration_bucket = _classify_duration(duration_ms)
    duration_seconds = duration_ms / 1000.0 if isinstance(
        duration_ms, int) and duration_ms >= 0 else 0.0

    # ── Step 4: Render plan ready ────────────────────────────────
    return KsoRenderPlanResult(
        status=STATUS_OK,
        render_action=RENDER_ACTION_RENDER,
        play_allowed=True,
        reason=REASON_READY_TO_RENDER,
        decision_reason=decision_reason,
        selected_present=True,
        media_type=media_type,
        duration_bucket=duration_bucket,
        pop_event_should_be_written=True,
        _selected_item=selected_item,
        _duration_seconds=duration_seconds,
    )


def format_kso_render_plan_result(result: KsoRenderPlanResult) -> str:
    """Format a KsoRenderPlanResult as a safe human-readable string.

    Never contains internal fields, paths, IDs, secrets, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"render_action: {result.render_action}",
        f"play_allowed: {str(result.play_allowed).lower()}",
        f"reason: {result.reason}",
        f"decision_reason: {result.decision_reason}",
        f"selected_present: {str(result.selected_present).lower()}",
        f"media_type: {result.media_type}",
        f"duration_bucket: {result.duration_bucket}",
        f"pop_event_should_be_written: "
        f"{str(result.pop_event_should_be_written).lower()}",
    ]
    return "\n".join(lines)
