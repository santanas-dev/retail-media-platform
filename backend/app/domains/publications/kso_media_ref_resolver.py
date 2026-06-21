"""KSO Safe MediaRef Resolver Core.

Pure function: maps a safe mediaRef (e.g. "media/current/slot-000")
back to the internal media source needed for future sidecar download.

This is the reverse of build_kso_safe_manifest_projection():
  - Projection: internal item → sorted → slot-000, slot-001, ...
  - Resolver:   "slot-002" → locate the same sorted item → return internal source

Applies the EXACT same KSO filters as the projection builder to ensure
deterministic slot assignment. Internal source (rendition_id) is ONLY
available as a private field — never in repr/format/public output.

No database, no HTTP, no FastAPI, no media bytes read.
"""

import re as _re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from app.domains.publications.kso_manifest_projection import (
    KSO_CHANNEL_CODE,
    ALLOWED_CONTENT_TYPES,
    _validate_content_type,
    _validate_safe_code,
    _validate_duration_ms,
    _build_media_ref,
    MAX_ITEMS,
    ManifestSourceItem,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

MEDIA_REF_PREFIX = "media/current/slot-"

# Strict slot pattern: media/current/slot-NNN where NNN is 000-999
_MEDIA_REF_SLOT_PATTERN = _re.compile(
    r"^media/current/slot-(\d{3})$"
)

_UNSAFE_IN_MEDIA_REF = frozenset({
    "..", "~", "\\", "://", "file:", "http:", "https:",
    "%2e", "%2f", "%2E", "%2F",
})

# Result statuses
STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_NOT_FOUND = "not_found"

REASON_RESOLVED = "resolved"
REASON_NOT_FOUND = "media_ref_not_found"
REASON_NO_VALID_ITEMS = "no_valid_items"
REASON_UNSAFE_MEDIA_REF = "unsafe_media_ref"
REASON_INVALID_ARGS = "invalid_args"

CONTENT_TYPE_NONE = "none"


# ══════════════════════════════════════════════════════════════════════
# Input type — extends ManifestSourceItem with internal source
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoMediaRefSourceItem:
    """Source item with internal media source for resolver.

    Extends ManifestSourceItem fields with an internal rendition_id.
    rendition_id is NEVER exposed in safe output — it's only for
    sidecar's future media download (by ID, not by manifest field).
    """

    # ── Filter/categorisation fields (same as ManifestSourceItem) ──
    channel_code: str = ""
    campaign_status: str = ""
    creative_status: str = ""
    rendition_status: str = ""
    publication_status: str = ""
    device_status: str = ""
    store_is_active: bool = False
    store_code: str = ""
    device_code: str = ""

    content_type: str = ""
    duration_ms: int = 0
    slot_order: int = 0

    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    now: Optional[datetime] = None

    # ── Internal source (NOT exposed in safe output) ──────────────
    # rendition_id: str — internal UUID for future media download
    internal_source_rendition_id: str = ""


# ══════════════════════════════════════════════════════════════════════
# Output types
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoMediaRefResolutionResult:
    """Safe result of resolving a mediaRef to an internal media source.

    Public safe fields only. Internal fields (repr=False) are NEVER
    exposed in repr, format, stdout, stderr, or errors.
    """

    status: str = STATUS_ERROR
    resolved: bool = False
    reason: str = REASON_INVALID_ARGS
    content_type: str = CONTENT_TYPE_NONE
    slot_index: Optional[int] = None
    items_total: int = 0
    valid_items: int = 0

    # Internal fields — NEVER exposed in safe output
    _internal_source_rendition_id: str = field(default="", repr=False)
    _internal_content_length: int = field(default=0, repr=False)
    _errors: List[str] = field(default_factory=list, repr=False)

    def __repr__(self) -> str:
        return (
            f"KsoMediaRefResolutionResult("
            f"status={self.status!r}, "
            f"resolved={self.resolved}, "
            f"reason={self.reason!r}, "
            f"content_type={self.content_type!r}, "
            f"slot_index={self.slot_index}, "
            f"items_total={self.items_total}, "
            f"valid_items={self.valid_items})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers — mediaRef validation
# ══════════════════════════════════════════════════════════════════════

def _validate_media_ref_slot(media_ref: str) -> Optional[int]:
    """Validate mediaRef as a safe slot reference.

    Returns the slot index (int) if valid, None otherwise.
    Accepts only: media/current/slot-000 through slot-999.

    Rejects: path traversal, absolute paths, URLs, backslashes.
    """
    if not isinstance(media_ref, str) or not media_ref.strip():
        return None

    # Must not start with /
    if media_ref.startswith("/"):
        return None

    # Check for unsafe substrings
    lower = media_ref.lower()
    for unsafe in _UNSAFE_IN_MEDIA_REF:
        if unsafe in lower:
            return None

    # Must match strict slot pattern
    match = _MEDIA_REF_SLOT_PATTERN.match(media_ref)
    if not match:
        return None

    slot = int(match.group(1))
    if slot < 0 or slot > 999:
        return None

    return slot


# ══════════════════════════════════════════════════════════════════════
# Core API
# ══════════════════════════════════════════════════════════════════════

def resolve_kso_media_ref_source(
    items: List[KsoMediaRefSourceItem],
    media_ref: str,
    generated_at: Optional[datetime] = None,
) -> KsoMediaRefResolutionResult:
    """Resolve a safe KSO mediaRef to its internal media source.

    Applies the EXACT same filters as build_kso_safe_manifest_projection():
      1. channel=kso only
      2. campaign_status=approved
      3. creative_status=approved
      4. rendition_status=valid
      5. publication_status=published
      6. device_status in (pending, active, lost)
      7. store_is_active=True
      8. content_type in allowlist (image/png, image/jpeg, video/mp4)
      9. valid_to < now → excluded
     10. valid_from > now → excluded
     11. unsafe store/device codes → excluded

    Then:
      - Sorts by (slot_order, content_type) — same as projection
      - Assigns deterministic mediaRef slots (slot-000, slot-001, ...)
      - Looks up the requested media_ref
      - Returns internal rendition_id as a private field

    Args:
        items: List of KsoMediaRefSourceItem (same filter fields as ManifestSourceItem,
               plus internal_source_rendition_id).
        media_ref: Safe slot reference, e.g. "media/current/slot-000".
        generated_at: Optional datetime for temporal filtering (defaults to now UTC).

    Returns:
        KsoMediaRefResolutionResult — safe aggregate, never raises.
    """
    errors: List[str] = []

    # ── Validate args ──────────────────────────────────────────────
    if not isinstance(items, list):
        return KsoMediaRefResolutionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    # ── Validate media_ref ─────────────────────────────────────────
    slot_index = _validate_media_ref_slot(media_ref)
    if slot_index is None:
        return KsoMediaRefResolutionResult(
            status=STATUS_ERROR,
            reason=REASON_UNSAFE_MEDIA_REF,
        )

    # ── Step 1: Apply KSO filters (same as projection builder) ─────
    filtered: List[KsoMediaRefSourceItem] = []

    for src in items:
        if not isinstance(src, KsoMediaRefSourceItem):
            continue

        # Channel
        if src.channel_code.strip().lower() != KSO_CHANNEL_CODE:
            continue

        # Campaign status
        if src.campaign_status.strip().lower() != "approved":
            continue

        # Creative status
        if src.creative_status.strip().lower() != "approved":
            continue

        # Rendition status
        if src.rendition_status.strip().lower() != "valid":
            continue

        # Publication status
        if src.publication_status.strip().lower() != "published":
            continue

        # Device status
        dev_status = src.device_status.strip().lower()
        if dev_status not in ("pending", "active", "lost"):
            continue

        # Store active
        if not src.store_is_active:
            continue

        # Content type
        if not _validate_content_type(src.content_type):
            continue

        # Temporal
        now = src.now or generated_at
        if src.valid_to is not None and src.valid_to < now:
            continue
        if src.valid_from is not None and src.valid_from > now:
            continue

        # Store/device codes — validate but don't exclude item if code is
        # unsafe (projection builder excludes at store_code assignment,
        # resolver only needs valid items with valid codes)
        if src.store_code.strip():
            err = _validate_safe_code(src.store_code.strip(), "store_code")
            if err:
                continue
        if src.device_code.strip():
            err = _validate_safe_code(src.device_code.strip(), "device_code")
            if err:
                continue

        # Must have internal source
        if not src.internal_source_rendition_id.strip():
            continue

        filtered.append(src)

    if not filtered:
        return KsoMediaRefResolutionResult(
            status=STATUS_ERROR,
            reason=REASON_NO_VALID_ITEMS,
            items_total=len(items),
            valid_items=0,
        )

    # ── Step 2: Sort (same as projection builder) ──────────────────
    # Projection sorts by (slotOrder, contentType)
    filtered.sort(key=lambda it: (
        max(0, it.slot_order),
        it.content_type.strip().lower(),
    ))

    # ── Step 3: Assign deterministic slots ─────────────────────────
    # Same as projection: index 0 → slot-000, index 1 → slot-001, etc.
    slot_map: dict[int, KsoMediaRefSourceItem] = {}
    for i, item in enumerate(filtered):
        if i >= MAX_ITEMS:
            break
        slot_map[i] = item

    # ── Step 4: Lookup ─────────────────────────────────────────────
    if slot_index not in slot_map:
        return KsoMediaRefResolutionResult(
            status=STATUS_NOT_FOUND,
            reason=REASON_NOT_FOUND,
            items_total=len(items),
            valid_items=len(filtered),
        )

    resolved_item = slot_map[slot_index]

    return KsoMediaRefResolutionResult(
        status=STATUS_OK,
        resolved=True,
        reason=REASON_RESOLVED,
        content_type=resolved_item.content_type.strip().lower(),
        slot_index=slot_index,
        items_total=len(items),
        valid_items=len(filtered),
        _internal_source_rendition_id=resolved_item.internal_source_rendition_id,
    )


# ══════════════════════════════════════════════════════════════════════
# Formatter
# ══════════════════════════════════════════════════════════════════════

def format_kso_media_ref_resolution_result(
    result: KsoMediaRefResolutionResult,
) -> str:
    """Format resolution result as safe human-readable string.

    NEVER contains: rendition_id, storage key, mediaRef value,
    raw JSON, IDs, paths, exception text, stacktrace.
    """
    lines = [
        f"status: {result.status}",
        f"resolved: {str(result.resolved).lower()}",
        f"reason: {result.reason}",
        f"content_type: {result.content_type}",
        f"slot_index: {result.slot_index}",
        f"items_total: {result.items_total}",
        f"valid_items: {result.valid_items}",
    ]
    return "\n".join(lines)
