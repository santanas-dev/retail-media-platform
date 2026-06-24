"""Screensaver Creative Payload — safe bridge from manifest/playlist to X11 screensaver runner.

Converts sidecar-saved safe playlist items into a ScreensaverCreativePayload
that the X11 runner can consume without exposing:
  - raw UUID / file_path / sha256 / storage_ref / minio
  - backend URL / token / secret / device_secret
  - receipt / payment / fiscal / customer / card / items / scanner

Design: docs/audit/x11-screensaver-manifest-integration-design.md
Prerequisite: 38.1.11.1 — Post-rollback UKM5 focus restore.
"""

from dataclasses import dataclass, field
from typing import Optional

from kso_player.playlist import PlayerPlaylistItem, PlayerPlaylist

from kso_player.screensaver_media_availability import (
    ScreensaverMediaAvailability,
    REASON_MEDIA_AVAILABLE,
    REASON_MEDIA_MISSING,
    REASON_INVALID_MEDIA_REF,
    REASON_NO_MEDIA_REF,
    REASON_CACHE_UNAVAILABLE,
    REASON_MANIFEST_NOT_FOUND,
    REASON_NO_MATCHING_ITEM,
    REASON_MEDIA_FILE_CORRUPT,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

MODULE_NAME = "screensaver_creative"
MODULE_VERSION = "0.1.0"

# — Allowed content types for screensaver —
ALLOWED_SCREENSAVER_CONTENT_TYPES = frozenset({
    "image/png",
    "image/jpeg",
    "video/mp4",
    "test",  # proof/test screens
})

# — Forbidden in content_type —
FORBIDDEN_CONTENT_TYPES = frozenset({
    "audio/", "audio/mpeg", "audio/ogg", "audio/wav", "audio/aac",
    "application/", "text/",
})

# — Hard max duration for screensaver creative (ms) —
MAX_DURATION_MS = 120_000  # 2 minutes
MIN_DURATION_MS = 1_000     # 1 second

# — Forbidden patterns in any creative field —
CREATIVE_FORBIDDEN_PATTERNS = frozenset({
    "file://", "http://", "https://",
    "127.0.0.1", "localhost",
    "backend_url", "backend_base_url",
    "token", "secret", "api_key", "password",
    "access_token", "refresh_token", "bearer", "jwt",
    "device_secret", "device_token",
    "sha256:", "sha256=", "minio:", "s3://",
    "/mnt/", "/media/", "/var/lib/",
    "receipt", "payment", "fiscal",
    "customer", "card", "pan",
    "barcode", "scanner", "key_value",
    "event_key", "event_code",
})

# — Visibility constants —
VIS_REASON_EMPTY_PLAYLIST = "empty_playlist"
VIS_REASON_NO_VALID_CREATIVE = "no_valid_creative"
VIS_REASON_CREATIVE_EXPIRED = "creative_expired"
VIS_REASON_CREATIVE_VALID = "creative_valid"
VIS_REASON_MEDIA_MISSING = "hidden_media_missing"
VIS_REASON_INVALID_MEDIA_REF = "hidden_invalid_media_ref"
VIS_REASON_CACHE_UNAVAILABLE = "hidden_cache_unavailable"


# ══════════════════════════════════════════════════════════════════════
# Safe Creative Payload
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ScreensaverCreativePayload:
    """Safe creative payload for X11 screensaver runner.

    Contains ONLY safe fields. No raw UUID, file_path, sha256,
    storage_ref, minio, backend_url, tokens, secrets.
    """

    creative_code: str = ""       # safe identifier from backend, or synthetic fallback
    media_ref: str = ""           # local-safe alias: "slot-000"
    content_type: str = "test"    # image/png, image/jpeg, video/mp4, or test
    duration_ms: int = 10_000     # bounded: 1000..120000
    slot_order: int = 0
    valid_from: Optional[str] = None   # ISO8601 UTC, optional
    valid_to: Optional[str] = None     # ISO8601 UTC, optional
    is_synthetic: bool = False    # True if creative_code was auto-generated (fallback)

    def __post_init__(self):
        if self.duration_ms < MIN_DURATION_MS:
            object.__setattr__(self, "duration_ms", MIN_DURATION_MS)
        if self.duration_ms > MAX_DURATION_MS:
            object.__setattr__(self, "duration_ms", MAX_DURATION_MS)

    @property
    def is_valid(self) -> bool:
        """True if all fields pass safety validation."""
        result = validate_screensaver_creative(self)
        return result["valid"]

    @property
    def is_expired(self) -> bool:
        """True if valid_to is set and in the past. False if valid_to is None."""
        if self.valid_to is None:
            return False
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            valid_to_dt = datetime.fromisoformat(self.valid_to)
            return now > valid_to_dt
        except Exception:
            return True  # unparseable date → treat as expired

    def to_safe_dict(self) -> dict:
        """Return a dict safe for logging — no forbidden fields."""
        d = {
            "creative_code": self.creative_code,
            "media_ref": self.media_ref,
            "content_type": self.content_type,
            "duration_ms": self.duration_ms,
            "slot_order": self.slot_order,
            "is_synthetic": self.is_synthetic,
        }
        if self.valid_from:
            d["valid_from"] = self.valid_from
        if self.valid_to:
            d["valid_to"] = self.valid_to
        return d


# ══════════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden_patterns(value: str, field_name: str) -> list[str]:
    """Return list of forbidden patterns found in value."""
    errors = []
    lower = value.lower()
    for pattern in CREATIVE_FORBIDDEN_PATTERNS:
        if pattern.lower() in lower:
            errors.append(
                f"Field '{field_name}' contains forbidden pattern '{pattern}'"
            )
    return errors


def validate_screensaver_creative(
    creative: ScreensaverCreativePayload,
) -> dict:
    """Validate a screensaver creative payload against safety rules.

    Returns:
        {"valid": bool, "errors": [str], "warnings": [str]}
    """
    errors = []
    warnings = []

    # — content_type —
    if not creative.content_type:
        errors.append("content_type is empty")
    elif creative.content_type not in ALLOWED_SCREENSAVER_CONTENT_TYPES:
        # Check if it starts with a forbidden type
        is_forbidden = any(
            creative.content_type.startswith(ft)
            for ft in FORBIDDEN_CONTENT_TYPES
        )
        if is_forbidden:
            errors.append(
                f"content_type '{creative.content_type}' is forbidden"
            )
        else:
            errors.append(
                f"content_type '{creative.content_type}' not in allowed set"
            )

    # — audio check —
    if creative.content_type.startswith("audio/"):
        errors.append(
            f"Audio content_types are forbidden: '{creative.content_type}'"
        )

    # — creative_code —
    if not creative.creative_code:
        warnings.append("creative_code is empty (allowed for test)")
    else:
        code_errors = _check_forbidden_patterns(
            creative.creative_code, "creative_code"
        )
        errors.extend(code_errors)

    # — media_ref —
    if not creative.media_ref:
        warnings.append("media_ref is empty (allowed for test)")
    else:
        ref_errors = _check_forbidden_patterns(
            creative.media_ref, "media_ref"
        )
        errors.extend(ref_errors)

    # — Forbidden field check: audit entire payload —
    payload_str = str(creative.to_safe_dict()).lower()
    for forbidden in [
        "uuid", "file_path", "storage_ref", "minio",
        "backend_url", "backend_host", "backend_port",
        "token", "secret", "device_secret",
        "receipt", "payment", "fiscal", "customer",
        "card", "pan", "barcode", "scanner",
    ]:
        if forbidden in payload_str:
            errors.append(
                f"Forbidden pattern '{forbidden}' found in creative payload"
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ══════════════════════════════════════════════════════════════════════
# Adapter: PlayerPlaylistItem → ScreensaverCreativePayload
# ══════════════════════════════════════════════════════════════════════

def build_screensaver_creative(
    item: PlayerPlaylistItem,
    creative_code: str = "",
    valid_from: Optional[str] = None,
    valid_to: Optional[str] = None,
) -> ScreensaverCreativePayload:
    """Convert a safe PlayerPlaylistItem into a ScreensaverCreativePayload.

    Prefers item.creative_code (from backend manifest) over the creative_code
    parameter. Falls back to synthetic code ONLY when no real creative_code
    is available.

    Extracts only safe fields: media_ref, content_type, duration_ms, slot_order.
    Strips: manifest_item_id (UUID), filename, sha256, size_bytes.

    Args:
        item: PlayerPlaylistItem from the existing playlist builder.
        creative_code: Fallback creative identifier (used only if item has none).
        valid_from: Optional ISO8601 UTC start.
        valid_to: Optional ISO8601 UTC end.

    Returns:
        ScreensaverCreativePayload (always succeeds, never raises).
    """
    if not isinstance(item, PlayerPlaylistItem):
        return ScreensaverCreativePayload(
            creative_code=creative_code or "invalid",
            content_type="test",
            duration_ms=10_000,
            is_synthetic=True,
        )

    # Build safe media_ref: strip path components, keep alias
    media_ref = item.media_ref or ""
    # Remove any path traversal
    if "/" in media_ref:
        media_ref = media_ref.rsplit("/", 1)[-1]

    # — Resolve creative_code: backend first, fallback only when missing —
    code = ""
    is_synthetic = False

    if item.creative_code and isinstance(item.creative_code, str) and item.creative_code.strip():
        # Backend creative_code takes priority
        code = item.creative_code.strip()
        is_synthetic = False
    elif creative_code and creative_code.strip():
        code = creative_code.strip()
        is_synthetic = True  # caller-provided code is fallback
    elif media_ref:
        code = f"scr-{media_ref}"
        is_synthetic = True
    else:
        code = f"scr-slot-{item.slot_order:03d}"
        is_synthetic = True

    # Validate content_type
    content_type = item.content_type or "test"
    if content_type not in ALLOWED_SCREENSAVER_CONTENT_TYPES:
        # Try to salvage: if it's a known image/video type, accept
        if content_type.startswith("image/") or content_type.startswith("video/"):
            pass  # keep as-is, validator will warn
        else:
            content_type = "test"

    # Bound duration
    duration_ms = item.duration_ms or 10_000
    if duration_ms < MIN_DURATION_MS:
        duration_ms = MIN_DURATION_MS
    elif duration_ms > MAX_DURATION_MS:
        duration_ms = MAX_DURATION_MS

    return ScreensaverCreativePayload(
        creative_code=code,
        media_ref=media_ref,
        content_type=content_type,
        duration_ms=duration_ms,
        slot_order=item.slot_order,
        valid_from=valid_from,
        valid_to=valid_to,
        is_synthetic=is_synthetic,
    )


def build_screensaver_creative_from_playlist(
    playlist: PlayerPlaylist,
    slot_order: int = 0,
    creative_code: str = "",
    valid_from: Optional[str] = None,
    valid_to: Optional[str] = None,
) -> ScreensaverCreativePayload:
    """Pick the first valid item from a playlist and convert to creative.

    If playlist is empty or has no ready items, returns a fallback
    ScreensaverCreativePayload with content_type="test" and is_valid=False.

    Args:
        playlist: PlayerPlaylist from build_playlist().
        slot_order: Target slot to pick (default: 0 = first item).
        creative_code: Optional stable identifier.
        valid_from/valid_to: Optional validity window.

    Returns:
        ScreensaverCreativePayload (always succeeds, never raises).
    """
    if not isinstance(playlist, PlayerPlaylist):
        return ScreensaverCreativePayload(
            creative_code="fallback",
            content_type="test",
            duration_ms=10_000,
        )

    if not playlist.ready or not playlist.items:
        return ScreensaverCreativePayload(
            creative_code="fallback",
            content_type="test",
            duration_ms=10_000,
        )

    # Find item by slot_order
    target = None
    for item in playlist.items:
        if isinstance(item, PlayerPlaylistItem) and item.slot_order == slot_order:
            target = item
            break

    # Fallback: take first item
    if target is None and playlist.items:
        for item in playlist.items:
            if isinstance(item, PlayerPlaylistItem):
                target = item
                break

    if target is None:
        return ScreensaverCreativePayload(
            creative_code="fallback",
            content_type="test",
            duration_ms=10_000,
        )

    return build_screensaver_creative(
        target,
        creative_code=creative_code,  # fallback only — item.creative_code wins
        valid_from=valid_from,
        valid_to=valid_to,
    )


# ══════════════════════════════════════════════════════════════════════
# Creative visibility — integrates with runner
# ══════════════════════════════════════════════════════════════════════

def decide_creative_visibility(
    creative: ScreensaverCreativePayload,
    playlist: Optional[PlayerPlaylist] = None,
    state: str = "idle",
    kill_switch_active: bool = False,
    media_availability=None,
) -> tuple[bool, str]:
    """Decide whether screensaver creative should be visible.

    Integrates creative validity with runner visibility logic and
    sidecar media cache availability (dev-only bridge).

    Priority:
        1. kill_switch_active → hidden
        2. state != idle → hidden
        3. playlist empty/not-ready → hidden (fallback)
        4. creative invalid → hidden
        5. creative expired → hidden
        6. media availability check (if provided):
           - media missing → hidden_media_missing
           - invalid ref → hidden_invalid_media_ref
           - cache unavailable → hidden_cache_unavailable
        7. idle + valid creative + media available + kill inactive → visible

    Args:
        creative: ScreensaverCreativePayload.
        playlist: Optional PlayerPlaylist for playlist-level checks.
        state: KSO state string.
        kill_switch_active: Kill-switch status.
        media_availability: Optional ScreensaverMediaAvailability result
            from check_screensaver_media_availability(). When None,
            media availability is not checked (backward compatible).

    Returns:
        (should_show: bool, reason: str)
    """
    if kill_switch_active:
        return False, "hidden_kill_switch"

    if state != "idle":
        return False, "hidden_state"

    if playlist is not None:
        if not isinstance(playlist, PlayerPlaylist):
            return False, VIS_REASON_EMPTY_PLAYLIST
        if not playlist.ready or not playlist.items:
            return False, VIS_REASON_EMPTY_PLAYLIST

    validation = validate_screensaver_creative(creative)
    if not validation["valid"]:
        return False, VIS_REASON_NO_VALID_CREATIVE

    if creative.is_expired:
        return False, VIS_REASON_CREATIVE_EXPIRED

    # — Media availability gate (dev-only bridge, skipped when None) —
    if media_availability is not None:
        if not isinstance(media_availability, ScreensaverMediaAvailability):
            return False, VIS_REASON_CACHE_UNAVAILABLE
        if not media_availability.ready_for_runner:
            # Map availability reason to visibility reason
            reason_map = {
                REASON_MEDIA_MISSING: VIS_REASON_MEDIA_MISSING,
                REASON_INVALID_MEDIA_REF: VIS_REASON_INVALID_MEDIA_REF,
                REASON_NO_MEDIA_REF: VIS_REASON_MEDIA_MISSING,
                REASON_CACHE_UNAVAILABLE: VIS_REASON_CACHE_UNAVAILABLE,
                REASON_MANIFEST_NOT_FOUND: VIS_REASON_CACHE_UNAVAILABLE,
                REASON_NO_MATCHING_ITEM: VIS_REASON_MEDIA_MISSING,
                REASON_MEDIA_FILE_CORRUPT: VIS_REASON_MEDIA_MISSING,
            }
            vis_reason = reason_map.get(
                media_availability.reason,
                VIS_REASON_CACHE_UNAVAILABLE,
            )
            return False, vis_reason

    return True, VIS_REASON_CREATIVE_VALID


# ══════════════════════════════════════════════════════════════════════
# Safe local PoP event contract (draft only — no backend send)
# ══════════════════════════════════════════════════════════════════════

SCREENSAVER_EVENT_VISIBLE = "screen_visible"
SCREENSAVER_EVENT_HIDDEN = "screen_hidden"
SCREENSAVER_EVENT_PLAYBACK_STARTED = "playback_started"
SCREENSAVER_EVENT_PLAYBACK_COMPLETED = "playback_completed"
SCREENSAVER_EVENT_BLOCKED = "blocked"

SCREENSAVER_EVENT_TYPES = frozenset({
    SCREENSAVER_EVENT_VISIBLE,
    SCREENSAVER_EVENT_HIDDEN,
    SCREENSAVER_EVENT_PLAYBACK_STARTED,
    SCREENSAVER_EVENT_PLAYBACK_COMPLETED,
    SCREENSAVER_EVENT_BLOCKED,
})


@dataclass(frozen=True)
class ScreensaverPoPDraft:
    """Safe local Proof-of-Play event draft for screensaver runner.

    NEVER sent to backend. Pure contract — no file I/O, no HTTP.
    Contains ONLY safe fields. No barcode, receipt, payment, fiscal,
    customer, card, items, scanner values.
    """

    event_type: str = SCREENSAVER_EVENT_VISIBLE
    creative_code: str = ""
    visible: bool = False
    state: str = "unknown"
    kill_switch_active: bool = False
    reason: str = ""
    duration_ms: int = 0
    started_at_utc: str = ""   # ISO8601
    ended_at_utc: str = ""     # ISO8601
    media_available: bool = False  # True if sidecar cache had media

    def __post_init__(self):
        if self.event_type not in SCREENSAVER_EVENT_TYPES:
            object.__setattr__(self, "event_type", SCREENSAVER_EVENT_HIDDEN)

    def to_safe_dict(self) -> dict:
        """Return safe dict — no forbidden fields."""
        d = {
            "event_type": self.event_type,
            "creative_code": self.creative_code,
            "visible": self.visible,
            "state": self.state,
            "kill_switch_active": self.kill_switch_active,
            "reason": self.reason,
            "duration_ms": self.duration_ms,
            "media_available": self.media_available,
        }
        if self.started_at_utc:
            d["started_at_utc"] = self.started_at_utc
        if self.ended_at_utc:
            d["ended_at_utc"] = self.ended_at_utc
        return d


def build_screensaver_pop_draft(
    creative: ScreensaverCreativePayload,
    event_type: str = SCREENSAVER_EVENT_VISIBLE,
    visible: bool = False,
    state: str = "idle",
    kill_switch_active: bool = False,
    reason: str = "",
    duration_ms: int = 0,
    started_at_utc: str = "",
    ended_at_utc: str = "",
    media_available: bool = False,
) -> ScreensaverPoPDraft:
    """Build a safe screensaver PoP draft event.

    Pure contract — no file I/O, no HTTP, no backend.
    NEVER includes: barcode, receipt, payment, fiscal, customer,
    card, scanner_value, backend_url, token, secret.

    Args:
        creative: ScreensaverCreativePayload shown/hidden.
        event_type: screen_visible / screen_hidden / playback_started
                   / playback_completed / blocked.
        visible: Whether creative was actually shown.
        state: KSO state at event time.
        kill_switch_active: Kill-switch status.
        reason: Visibility reason.
        duration_ms: Actual display duration (0 if hidden).
        started_at_utc: ISO8601 start timestamp.
        ended_at_utc: ISO8601 end timestamp.
        media_available: Whether sidecar cache had media file ready.

    Returns:
        ScreensaverPoPDraft (always safe, never raises).
    """
    if event_type not in SCREENSAVER_EVENT_TYPES:
        event_type = SCREENSAVER_EVENT_HIDDEN

    code = creative.creative_code if isinstance(creative, ScreensaverCreativePayload) else ""

    return ScreensaverPoPDraft(
        event_type=event_type,
        creative_code=code,
        visible=visible,
        state=state,
        kill_switch_active=kill_switch_active,
        reason=reason,
        duration_ms=duration_ms,
        started_at_utc=started_at_utc,
        ended_at_utc=ended_at_utc,
        media_available=media_available,
    )


# ══════════════════════════════════════════════════════════════════════
# PoP safety validation
# ══════════════════════════════════════════════════════════════════════

POP_FORBIDDEN_FIELDS = frozenset({
    "barcode", "scanner_value", "key_value", "event_key", "event_code",
    "receipt_id", "transaction_id", "payment_amount", "payment_method",
    "fiscal_data", "customer_name", "customer_id", "customer_phone",
    "customer_email", "card_number", "pan", "items", "total_amount",
    "cashier_id", "cashier_name", "receipt_number",
    "backend_url", "token", "secret", "api_key", "password",
    "device_secret", "device_token", "access_token",
    "file_path", "storage_ref", "minio", "sha256",
})


def validate_screensaver_pop_safety(data: dict) -> dict:
    """Validate that a screensaver PoP draft contains no forbidden fields.

    Returns:
        {"valid": bool, "errors": [str]}
    """
    errors = []
    if not isinstance(data, dict):
        return {"valid": False, "errors": ["data must be a dict"]}

    for key in data:
        key_lower = key.lower()
        if key_lower in POP_FORBIDDEN_FIELDS:
            errors.append(f"forbidden field in PoP: {key}")
        for pattern in [
            "barcode", "scanner", "receipt", "payment", "fiscal",
            "customer", "card", "pan", "token", "secret",
            "backend", "minio", "sha256", "file_path",
        ]:
            if pattern in key_lower and key not in errors:
                errors.append(f"forbidden-like field in PoP: {key}")
                break

    return {"valid": len(errors) == 0, "errors": errors}
