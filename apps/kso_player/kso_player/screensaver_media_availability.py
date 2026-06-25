"""Screensaver Media Availability — bridge between sidecar cache and X11 runner.

Checks whether a ScreensaverCreativePayload has actual media available
in the sidecar's local media/current/ cache.

Dev-only bridge:
  - Reads sidecar's manifest/current_manifest.json to find filename by slot_order.
  - Checks file existence in media/current/ (sha256 verification optional).
  - No network, no backend, no KSO, no X11, no Chromium.

Design: docs/audit/x11-runner-sidecar-cache-bridge-design.md
Prerequisite: 38.2.1 — creative_code preservation.
"""

import json as _json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

MODULE_NAME = "screensaver_media_availability"
MODULE_VERSION = "0.1.0"

# — Availability reasons —
REASON_MEDIA_AVAILABLE = "media_available"
REASON_MEDIA_MISSING = "media_missing"
REASON_INVALID_MEDIA_REF = "invalid_media_ref"
REASON_NO_MEDIA_REF = "no_media_ref"
REASON_CACHE_UNAVAILABLE = "cache_unavailable"
REASON_MANIFEST_NOT_FOUND = "manifest_not_found"
REASON_NO_MATCHING_ITEM = "no_matching_item"
REASON_MEDIA_FILE_CORRUPT = "media_file_corrupt"

# — All allowed reasons —
ALL_AVAILABILITY_REASONS = frozenset({
    REASON_MEDIA_AVAILABLE,
    REASON_MEDIA_MISSING,
    REASON_INVALID_MEDIA_REF,
    REASON_NO_MEDIA_REF,
    REASON_CACHE_UNAVAILABLE,
    REASON_MANIFEST_NOT_FOUND,
    REASON_NO_MATCHING_ITEM,
    REASON_MEDIA_FILE_CORRUPT,
})

# — Forbidden substrings in media_ref —
_MEDIA_REF_FORBIDDEN = frozenset({
    "..", "~", "\\\\", "://", "file:", "http:", "https:",
    "%2e", "%2f", "%2E", "%2F",
    "/mnt/", "/media/", "/var/", "/tmp/",
    "token", "secret", "password", "api_key",
})

_MEDIA_REF_SAFE_PATTERN = __import__("re").compile(r"^[a-z0-9][a-z0-9/_-]*$")

# — Relative path to manifest —
_MANIFEST_REL_PATH = "manifest/current_manifest.json"

# — Relative path to media cache —
_MEDIA_CURRENT_REL = "media/current"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ScreensaverMediaAvailability:
    """Result of checking whether a creative has media available in sidecar cache.

    Safe fields only. NEVER contains:
      - raw file_path / absolute path / storage_ref / sha256 / minio / s3
      - backend_url / token / secret / device_secret
      - receipt / payment / fiscal / customer / card / items / barcode / scanner_value
    """

    creative_code: str = ""
    media_ref: str = ""
    content_type: str = ""
    duration_ms: int = 0
    slot_order: int = 0
    ready_for_runner: bool = False
    reason: str = REASON_NO_MEDIA_REF

    # — Derived safe flags —
    media_available: bool = False
    """True only if media file was found and verified in cache."""

    def __post_init__(self):
        if self.reason not in ALL_AVAILABILITY_REASONS:
            object.__setattr__(self, "reason", REASON_CACHE_UNAVAILABLE)

    def to_safe_dict(self) -> dict:
        """Return safe dict — no paths, no secrets, no sensitive fields."""
        return {
            "creative_code": self.creative_code,
            "media_ref": self.media_ref,
            "content_type": self.content_type,
            "duration_ms": self.duration_ms,
            "slot_order": self.slot_order,
            "ready_for_runner": self.ready_for_runner,
            "reason": self.reason,
            "media_available": self.media_available,
        }


# ══════════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════════

def _validate_media_ref_safe(media_ref: str) -> bool:
    """Validate that media_ref contains no forbidden substrings and matches safe pattern."""
    if not isinstance(media_ref, str) or not media_ref.strip():
        return False
    # Must match safe pattern: starts with lowercase alphanum, no leading slash
    if not _MEDIA_REF_SAFE_PATTERN.match(media_ref):
        return False
    lower = media_ref.lower()
    for forbidden in _MEDIA_REF_FORBIDDEN:
        if forbidden in lower:
            return False
    return True


def _validate_availability_payload_safe(data: dict) -> List[str]:
    """Check dict for forbidden fields. Returns list of error strings."""
    errors = []
    forbidden_lower = {
        "file_path", "absolute_path", "storage_ref", "sha256", "minio", "s3",
        "backend_url", "token", "secret", "device_secret", "device_token",
        "access_token", "refresh_token", "bearer", "jwt",
        "receipt", "payment", "fiscal", "customer", "card", "pan",
        "barcode", "scanner_value", "key_value", "items",
    }
    if not isinstance(data, dict):
        return ["data must be a dict"]

    for key in data:
        key_lower = key.lower()
        for fb in forbidden_lower:
            if fb in key_lower:
                errors.append(f"forbidden field in availability: '{key}'")
                break
        if isinstance(data[key], str):
            val_lower = data[key].lower()
            for fb in forbidden_lower:
                if fb in val_lower:
                    errors.append(f"forbidden value in '{key}': contains '{fb}'")
                    break
    return errors


# ══════════════════════════════════════════════════════════════════════
# Core: check media availability
# ══════════════════════════════════════════════════════════════════════

def _read_manifest(agent_root: Path) -> Optional[dict]:
    """Read and parse current_manifest.json. Returns None on any error."""
    manifest_path = agent_root / _MANIFEST_REL_PATH
    if not manifest_path.exists():
        return None
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        return _json.loads(raw)
    except Exception:
        return None


def _find_manifest_item_by_order(
    manifest: dict,
    slot_order: int,
) -> Optional[dict]:
    """Find a manifest item whose 'order' matches slot_order."""
    items = manifest.get("items", [])
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        order = item.get("order")
        if isinstance(order, int) and order == slot_order:
            return item
    return None


def check_screensaver_media_availability(
    creative,
    agent_root,  # py36-compat: Union[str, Path] — use string annotation
    # str | Path not supported in Python 3.6
) -> ScreensaverMediaAvailability:
    """Check whether a creative has media available in the sidecar's local cache.

    Reads the sidecar's manifest/current_manifest.json to map
    slot_order → filename, then checks if media/current/<filename> exists.

    Does NOT verify sha256 or size (dev-only bridge).
    Does NOT access network, backend, KSO, X11, or Chromium.

    Args:
        creative: ScreensaverCreativePayload to check.
        agent_root: Sidecar agent root path (contains manifest/, media/).

    Returns:
        ScreensaverMediaAvailability — always safe, never raises.
    """
    from kso_player.screensaver_creative import ScreensaverCreativePayload

    if not isinstance(creative, ScreensaverCreativePayload):
        return ScreensaverMediaAvailability(
            creative_code="",
            reason=REASON_INVALID_MEDIA_REF,
        )

    agent_root = Path(agent_root)

    # — Validate media_ref safety —
    media_ref = creative.media_ref or ""
    if media_ref and not _validate_media_ref_safe(media_ref):
        return ScreensaverMediaAvailability(
            creative_code=creative.creative_code,
            media_ref=media_ref,
            content_type=creative.content_type,
            duration_ms=creative.duration_ms,
            slot_order=creative.slot_order,
            reason=REASON_INVALID_MEDIA_REF,
        )

    if not media_ref:
        # Test creative without media_ref — acceptable for test-only
        # Synthetic test creatives allowed without media; non-synthetic require media
        if creative.is_synthetic:
            return ScreensaverMediaAvailability(
                creative_code=creative.creative_code,
                media_ref="",
                content_type=creative.content_type,
                duration_ms=creative.duration_ms,
                slot_order=creative.slot_order,
                ready_for_runner=True,
                reason=REASON_NO_MEDIA_REF,
                media_available=False,
            )
        return ScreensaverMediaAvailability(
            creative_code=creative.creative_code,
            media_ref="",
            content_type=creative.content_type,
            duration_ms=creative.duration_ms,
            slot_order=creative.slot_order,
            ready_for_runner=False,
            reason=REASON_NO_MEDIA_REF,
            media_available=False,
        )

    # — Read manifest —
    manifest = _read_manifest(agent_root)
    if manifest is None:
        # Synthetic test creatives allowed even without manifest
        if creative.is_synthetic and creative.content_type == "test":
            return ScreensaverMediaAvailability(
                creative_code=creative.creative_code,
                media_ref=media_ref,
                content_type=creative.content_type,
                duration_ms=creative.duration_ms,
                slot_order=creative.slot_order,
                ready_for_runner=True,
                reason=REASON_CACHE_UNAVAILABLE,
                media_available=False,
            )
        return ScreensaverMediaAvailability(
            creative_code=creative.creative_code,
            media_ref=media_ref,
            content_type=creative.content_type,
            duration_ms=creative.duration_ms,
            slot_order=creative.slot_order,
            reason=REASON_MANIFEST_NOT_FOUND,
        )

    # — Find matching manifest item by slot_order —
    item = _find_manifest_item_by_order(manifest, creative.slot_order)
    if item is None:
        return ScreensaverMediaAvailability(
            creative_code=creative.creative_code,
            media_ref=media_ref,
            content_type=creative.content_type,
            duration_ms=creative.duration_ms,
            slot_order=creative.slot_order,
            reason=REASON_NO_MATCHING_ITEM,
        )

    # — Get filename from manifest item —
    filename = item.get("filename", "")
    if not isinstance(filename, str) or not filename.strip():
        return ScreensaverMediaAvailability(
            creative_code=creative.creative_code,
            media_ref=media_ref,
            content_type=creative.content_type,
            duration_ms=creative.duration_ms,
            slot_order=creative.slot_order,
            reason=REASON_MEDIA_MISSING,
        )

    # — Check file existence in media/current/ —
    media_path = agent_root / _MEDIA_CURRENT_REL / filename

    # Safety: ensure resolved path stays under agent_root/media/current/
    try:
        media_path_resolved = media_path.resolve()
        media_current_resolved = (agent_root / _MEDIA_CURRENT_REL).resolve()
        media_path_resolved.relative_to(media_current_resolved)
    except (ValueError, OSError):
        return ScreensaverMediaAvailability(
            creative_code=creative.creative_code,
            media_ref=media_ref,
            content_type=creative.content_type,
            duration_ms=creative.duration_ms,
            slot_order=creative.slot_order,
            reason=REASON_INVALID_MEDIA_REF,
        )

    # Symlink check — reject BEFORE existence (security: even dangling symlinks are unsafe)
    if media_path.is_symlink():
        return ScreensaverMediaAvailability(
            creative_code=creative.creative_code,
            media_ref=media_ref,
            content_type=creative.content_type,
            duration_ms=creative.duration_ms,
            slot_order=creative.slot_order,
            reason=REASON_INVALID_MEDIA_REF,
        )

    if not media_path.exists():
        return ScreensaverMediaAvailability(
            creative_code=creative.creative_code,
            media_ref=media_ref,
            content_type=creative.content_type,
            duration_ms=creative.duration_ms,
            slot_order=creative.slot_order,
            reason=REASON_MEDIA_MISSING,
        )

    if not media_path.is_file():
        return ScreensaverMediaAvailability(
            creative_code=creative.creative_code,
            media_ref=media_ref,
            content_type=creative.content_type,
            duration_ms=creative.duration_ms,
            slot_order=creative.slot_order,
            reason=REASON_MEDIA_FILE_CORRUPT,
        )

    # — Media available —
    return ScreensaverMediaAvailability(
        creative_code=creative.creative_code,
        media_ref=media_ref,
        content_type=creative.content_type,
        duration_ms=creative.duration_ms,
        slot_order=creative.slot_order,
        ready_for_runner=True,
        reason=REASON_MEDIA_AVAILABLE,
        media_available=True,
    )
