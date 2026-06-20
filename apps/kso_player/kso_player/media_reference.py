"""KSO Player Safe Local Media Reference Core — safe alias for HTML shell.

Builds a safe local media reference (mediaRef) from a selected playlist item.
The mediaRef is a whitelist-validated local alias like "media/current/slot-001".

NEVER exposes: absolute paths, real filenames, manifest IDs, campaign IDs,
creative IDs, schedule item IDs, sha256, backend URLs, tokens, secrets.

NO media bytes read, NO file open, NO backend, NO HTTP, NO Chromium.
"""

import re as _re
from dataclasses import dataclass
from typing import Optional

from kso_player.render_plan import (
    KsoRenderPlanResult,
    MEDIA_IMAGE, MEDIA_VIDEO, MEDIA_UNKNOWN,
    FORBIDDEN_SUBSTRINGS,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

MEDIA_REF_KIND_LOCAL_ALIAS = "local_alias"
MEDIA_REF_KIND_NONE = "none"

REASON_VALID_REFERENCE = "valid_reference"
REASON_UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
REASON_NO_SELECTED_ITEM = "no_selected_item"
REASON_UNSAFE_ALIAS = "unsafe_alias"
REASON_INVALID_ARGS = "invalid_args"
REASON_INTERNAL_ERROR = "internal_error"

# ── Media ref whitelist ──────────────────────────────────────────────

# Safe format: only lowercase alphanumeric, forward slash, underscore, hyphen
_MEDIA_REF_PATTERN = _re.compile(r"^[a-z0-9/_-]+$")

# Unsafe substrings that MUST NOT appear in mediaRef
_UNSAFE_IN_MEDIA_REF = frozenset({
    "..", "~", "\\", "://", "file:", "http:", "https:",
    "%2e", "%2f", "%2E", "%2F",
})

# Slot prefix
_SLOT_PREFIX = "media/current/slot-"


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoSafeMediaReferenceResult:
    """Safe media reference for the HTML shell.

    External safe fields only. Internal _media_ref is NEVER exposed
    in repr, format, stdout, stderr, or errors.

    media_ref is an alias like "media/current/slot-001" — NOT a real
    filename, NOT an absolute path, NOT an ID, NOT a hash.
    """

    status: str = STATUS_ERROR
    media_ref_present: bool = False
    media_ref_kind: str = MEDIA_REF_KIND_NONE
    media_type: str = MEDIA_UNKNOWN
    reason: str = REASON_INVALID_ARGS

    # Internal field — NEVER exposed in safe output
    _media_ref: str = ""

    def __repr__(self) -> str:
        return (
            f"KsoSafeMediaReferenceResult("
            f"status={self.status!r}, "
            f"media_ref_present={self.media_ref_present}, "
            f"media_ref_kind={self.media_ref_kind!r}, "
            f"media_type={self.media_type!r}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _validate_media_ref(media_ref: str) -> bool:
    """Validate that media_ref matches the safe whitelist.

    Must match ^[a-z0-9/_-]+$ and must not contain unsafe substrings.
    """
    if not isinstance(media_ref, str):
        return False
    if not media_ref.strip():
        return False
    if not _MEDIA_REF_PATTERN.match(media_ref):
        return False
    lower = media_ref.lower()
    for unsafe in _UNSAFE_IN_MEDIA_REF:
        if unsafe in lower:
            return False
    return True


def _build_slot_ref(order: int) -> str:
    """Build a safe slot reference from item order.

    Returns format: media/current/slot-{order:03d}
    """
    return f"{_SLOT_PREFIX}{order:03d}"


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def build_kso_safe_media_reference(
    selected_item,
) -> KsoSafeMediaReferenceResult:
    """Build a safe local media reference from a selected playlist item.

    Derives the mediaRef from the item's order field: media/current/slot-{order:03d}.
    The mediaRef is a local alias — NOT the real filename, ID, or hash.

    Validates the generated mediaRef against the whitelist before returning.

    Args:
        selected_item: A PlayerPlaylistItem from the playlist/ render plan.

    Returns:
        KsoSafeMediaReferenceResult — safe aggregate, never raises.
    """
    # ── Validate selected_item ────────────────────────────────────
    if selected_item is None:
        return KsoSafeMediaReferenceResult(
            status=STATUS_WARNING,
            reason=REASON_NO_SELECTED_ITEM,
        )

    # ── Check media type ──────────────────────────────────────────
    content_type = getattr(selected_item, "content_type", "")
    if not isinstance(content_type, str):
        return KsoSafeMediaReferenceResult(
            status=STATUS_WARNING,
            reason=REASON_UNSUPPORTED_MEDIA_TYPE,
        )
    ct = content_type.strip().lower()
    if ct.startswith("image/"):
        media_type = MEDIA_IMAGE
    elif ct.startswith("video/"):
        media_type = MEDIA_VIDEO
    else:
        return KsoSafeMediaReferenceResult(
            status=STATUS_WARNING,
            reason=REASON_UNSUPPORTED_MEDIA_TYPE,
        )

    # ── Build slot reference from order ───────────────────────────
    order = getattr(selected_item, "order", None)
    if not isinstance(order, int) or order < 0:
        return KsoSafeMediaReferenceResult(
            status=STATUS_WARNING,
            reason=REASON_NO_SELECTED_ITEM,
        )

    slot_ref = _build_slot_ref(order)

    # ── Whitelist validation ──────────────────────────────────────
    if not _validate_media_ref(slot_ref):
        return KsoSafeMediaReferenceResult(
            status=STATUS_ERROR,
            reason=REASON_UNSAFE_ALIAS,
        )

    return KsoSafeMediaReferenceResult(
        status=STATUS_OK,
        media_ref_present=True,
        media_ref_kind=MEDIA_REF_KIND_LOCAL_ALIAS,
        media_type=media_type,
        reason=REASON_VALID_REFERENCE,
        _media_ref=slot_ref,
    )


def build_kso_safe_media_reference_from_render_plan(
    render_plan: KsoRenderPlanResult,
) -> KsoSafeMediaReferenceResult:
    """Build a safe media reference from a render plan result.

    Extracts the internal _selected_item from the render plan and
    delegates to build_kso_safe_media_reference().

    Args:
        render_plan: A KsoRenderPlanResult with _selected_item populated.

    Returns:
        KsoSafeMediaReferenceResult — safe aggregate, never raises.
    """
    if render_plan is None:
        return KsoSafeMediaReferenceResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    selected_item = getattr(render_plan, "_selected_item", None)
    return build_kso_safe_media_reference(selected_item)


def format_kso_safe_media_reference_result(
    result: KsoSafeMediaReferenceResult,
) -> str:
    """Format a KsoSafeMediaReferenceResult as a safe human-readable string.

    Never contains absolute paths, filenames, IDs, hashes, or forbidden substrings.
    """
    lines = [
        f"status: {result.status}",
        f"media_ref_present: {str(result.media_ref_present).lower()}",
        f"media_ref_kind: {result.media_ref_kind}",
        f"media_type: {result.media_type}",
        f"reason: {result.reason}",
    ]
    return "\n".join(lines)
