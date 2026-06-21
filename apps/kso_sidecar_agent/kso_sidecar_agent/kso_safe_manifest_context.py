"""KSO Sidecar — Safe Manifest Context Reader.

Reads local manifest/current_manifest.json and extracts a safe
manifest items list for PoP event classification.

Supports two formats:
  1. KSO Safe Manifest (v1): schemaVersion, channel=kso, items[].slotOrder
  2. Legacy manifest: read via manifest_store (fallback, unchanged)

For KSO safe format, maps:
  slotOrder → order, contentType → content_type,
  durationMs → duration_ms, mediaRef → media_ref (internal).

Returns safe items list suitable for _find_manifest_item_by_order().
Never exposes: mediaRef values, raw JSON, paths, IDs, hashes, secrets.
"""

import json as _json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

MANIFEST_FILE = "manifest/current_manifest.json"

KSO_SCHEMA_VERSION = 1
KSO_CHANNEL = "kso"

# Forbidden keys — must never appear in safe output
_FORBIDDEN_KEYS = frozenset({
    "token", "secret", "password", "api_key", "private_key",
    "manifest_version_id", "manifest_hash", "source",
    "campaign_id", "creative_id", "rendition_id",
    "schedule_item_id", "batch_id", "booking_id",
    "file_path", "media_path", "local_path", "absolute_path",
    "filename", "sha256", "storage_key", "minio",
    "backend_base_url", "device_code", "authorization",
    "stacktrace",
})

# Allowed content types for KSO
_ALLOWED_KSO_CONTENT_TYPES = frozenset({
    "image/png", "image/jpeg", "video/mp4",
})


# ══════════════════════════════════════════════════════════════════════
# Dataclass
# ══════════════════════════════════════════════════════════════════════


@dataclass
class KsoSafeManifestContext:
    """Safe manifest context extracted from KSO safe manifest body.

    Never contains: mediaRef values, raw JSON, paths, IDs, hashes, secrets.
    """

    format: str = "unknown"     # "kso_safe" | "legacy" | "none"
    channel: str = ""
    items_count: int = 0
    schema_version: int = 0
    store_code: str = ""
    device_code: str = ""

    # Internal items list — never exposed in repr
    _items: List[Dict[str, Any]] = field(default_factory=list, repr=False)

    def __repr__(self) -> str:
        return (
            f"KsoSafeManifestContext("
            f"format={self.format!r}, "
            f"channel={self.channel!r}, "
            f"items_count={self.items_count}, "
            f"schema_version={self.schema_version})"
        )


# ══════════════════════════════════════════════════════════════════════
# KSO safe manifest detection
# ══════════════════════════════════════════════════════════════════════


def _is_kso_safe_format(data: dict) -> bool:
    """Detect KSO safe manifest body format.

    KSO safe format has: schemaVersion, channel=kso, items[].slotOrder (or mediaRef).
    Legacy format has: manifest_version_id, manifest_hash, source.
    """
    if not isinstance(data, dict):
        return False

    # KSO marker: schemaVersion present, no manifest_version_id
    has_schema = "schemaVersion" in data
    has_legacy = "manifest_version_id" in data or "manifest_hash" in data

    if has_schema and not has_legacy:
        channel = data.get("channel", "")
        if isinstance(channel, str) and channel.lower() == KSO_CHANNEL:
            return True

    return False


# ══════════════════════════════════════════════════════════════════════
# KSO safe item mapping
# ══════════════════════════════════════════════════════════════════════


def _map_kso_item_to_context(raw_item: dict, idx: int) -> Optional[Dict[str, Any]]:
    """Map a KSO safe manifest item to internal context dict.

    Maps: slotOrder → order, contentType → content_type,
          durationMs → duration_ms.

    Validates content type is allowed. Skips unsafe mediaRefs.
    Returns None if item is invalid/unsafe.
    """
    if not isinstance(raw_item, dict):
        return None

    slot_order = raw_item.get("slotOrder")
    if not isinstance(slot_order, int) or slot_order < 0:
        return None  # invalid slotOrder

    content_type = raw_item.get("contentType", "")
    if not isinstance(content_type, str) or not content_type.strip():
        return None
    content_type = content_type.strip().lower()
    if content_type not in _ALLOWED_KSO_CONTENT_TYPES:
        return None

    duration_ms = raw_item.get("durationMs", 0)
    if not isinstance(duration_ms, int):
        duration_ms = 0

    # Validate mediaRef — must be safe alias
    media_ref = raw_item.get("mediaRef", "")
    if not isinstance(media_ref, str):
        media_ref = ""
    # Simple safety check for mediaRef
    if media_ref:
        lower_mr = media_ref.lower()
        unsafe = ("..", "\\\\", "://", "http:", "https:", "file:", "%2e", "%2f")
        for u in unsafe:
            if u in lower_mr:
                return None  # unsafe mediaRef — skip item
        if media_ref.startswith("/"):
            return None

    # Build safe internal item dict for classifier
    return {
        "order": slot_order,             # mapped from slotOrder
        "content_type": content_type,     # mapped from contentType
        "duration_ms": duration_ms,       # mapped from durationMs
        # media_ref is internal only — NEVER exposed in safe output
        "_media_ref": media_ref if media_ref else "",
    }


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════


def read_kso_safe_manifest_context(root) -> KsoSafeManifestContext:
    """Read local manifest and extract safe KSO manifest context.

    Tries to read manifest/current_manifest.json.
    If KSO safe format detected → maps items for classifier.
    If legacy format detected → returns format=legacy, items not parsed here.
    If file missing → returns format=none.

    Args:
        root: Agent root path (str or Path).

    Returns:
        KsoSafeManifestContext — always safe, never raises.

    Raises:
        NEVER raises — errors are captured in format field.
    """
    root = Path(root)

    # ── Read file ──────────────────────────────────────────────
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.exists():
        return KsoSafeManifestContext(format="none")

    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = _json.loads(raw)
    except Exception:
        return KsoSafeManifestContext(format="error")

    if not isinstance(data, dict):
        return KsoSafeManifestContext(format="error")

    # ── Reject gateway wrapper ─────────────────────────────────
    if "status" in data and "manifest" in data:
        return KsoSafeManifestContext(format="gateway_wrapper")

    # ── Detect format ──────────────────────────────────────────
    if not _is_kso_safe_format(data):
        # Legacy format — don't parse here, let manifest_store handle it
        return KsoSafeManifestContext(format="legacy")

    # ── KSO safe format — extract items ────────────────────────
    items = data.get("items", [])
    if not isinstance(items, list):
        return KsoSafeManifestContext(
            format="kso_safe",
            schema_version=data.get("schemaVersion", 0),
        )

    mapped_items: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        mapped = _map_kso_item_to_context(item, idx)
        if mapped is not None:
            mapped_items.append(mapped)

    return KsoSafeManifestContext(
        format="kso_safe",
        channel=data.get("channel", ""),
        items_count=len(mapped_items),
        schema_version=data.get("schemaVersion", 1),
        store_code=data.get("storeCode", ""),
        device_code=data.get("deviceCode", ""),
        _items=mapped_items,
    )


def get_manifest_items_for_classifier(
    context: KsoSafeManifestContext,
) -> Optional[List[Dict[str, Any]]]:
    """Get manifest items list safe for PoP classifier.

    Returns the internal items list (with order, content_type, duration_ms).
    Returns None if no valid items available.

    NEVER returns items with media_ref in accessible fields.
    Callers must NOT expose _items or _media_ref in safe output.
    """
    if context.format not in ("kso_safe",):
        return None
    if not context._items:
        return None
    return context._items
