"""KSO Safe Manifest Projection Builder.

Pure function: takes publication/manifest source data and produces
a safe KSO player manifest. No database calls, no HTTP, no FastAPI.

This is the backend-core layer that strips internal IDs, backend paths,
and forbidden fields from the publication manifest, producing only the
safe player-visible fields defined in the KSO manifest export contract.

See: docs/architecture/kso-manifest-export-contract.md
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

KSO_CHANNEL_CODE = "kso"
MANIFEST_SCHEMA_VERSION = 1
MEDIA_REF_PREFIX = "media/current/slot-"
MAX_ITEMS = 1000
MAX_MANIFEST_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_DURATION_MS = 86_400_000  # 24 hours
MIN_DURATION_MS = 1

# Allowed MIME types for KSO v1
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset({
    "image/png",
    "image/jpeg",
    "video/mp4",
})

# Forbidden keys — MUST NOT appear in any player manifest
FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "access_token", "refresh_token", "token", "jwt",
    "password", "secret", "credential", "credentials",
    "authorization", "cookie", "api_key", "private_key", "public_key",
    "backend_base_url", "127.0.0.1", "device_secret",
    "manifest_item_id", "campaign_id", "creative_id",
    "rendition_id", "campaign_rendition_id",
    "schedule_item_id", "batch_id", "booking_id", "target_id",
    "inventory_unit_id", "logical_carrier_id", "display_surface_id",
    "file_path", "media_path", "local_path", "creatives/",
    "budget", "currency", "price",
    "customer_id", "phone", "email", "receipt_data",
    "card_number", "pan", "fiscal_data",
    "minio", "s3://", "bucket",
})

# Forbidden in store/device codes
_FORBIDDEN_CODE_PATTERNS = frozenset({"..", "/", "\\", " "})


# ══════════════════════════════════════════════════════════════════════
# Input / output types
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ManifestSourceItem:
    """One item from the publication manifest to project.

    Carries internal IDs (repr=False) for server-side correlation
    after projection — never exposed in KSO manifest output.
    """

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

    # ── Internal IDs for server-side PoP correlation ────────────────
    # Never exposed in KSO manifest — repr=False.
    _internal_manifest_item_id: Optional[str] = field(default=None, repr=False)
    _internal_manifest_version_id: Optional[str] = field(default=None, repr=False)
    _internal_publication_target_id: Optional[str] = field(default=None, repr=False)
    _internal_schedule_item_id: Optional[str] = field(default=None, repr=False)
    _internal_campaign_id: Optional[str] = field(default=None, repr=False)
    _internal_campaign_rendition_id: Optional[str] = field(default=None, repr=False)
    _internal_rendition_id: Optional[str] = field(default=None, repr=False)
    _internal_creative_version_id: Optional[str] = field(default=None, repr=False)


@dataclass
class KsoSafeManifestItem:
    """One safe item in the KSO player manifest."""

    slotOrder: int = 0
    contentType: str = ""
    durationMs: int = 0
    mediaRef: str = ""
    validFrom: str = ""
    validTo: str = ""


@dataclass
class KsoSafeManifestProjectionResult:
    """Result of building a KSO-safe manifest projection.

    Exposes only safe fields. The manifest dict contains the
    full JSON-encodable output. Internal counters are for audit
    only — never contain IDs, paths, or forbidden strings.
    """

    ok: bool = False
    manifest: Dict[str, Any] = field(default_factory=dict)
    items_included: int = 0
    items_excluded: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"KsoSafeManifestProjectionResult("
            f"ok={self.ok}, "
            f"items_included={self.items_included}, "
            f"items_excluded={self.items_excluded}, "
            f"errors={len(self.errors)}, "
            f"warnings={len(self.warnings)})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _validate_safe_code(value: str, field_name: str) -> Optional[str]:
    """Validate a store/device code is safe: ^[a-z0-9_-]+$ without path traversal."""
    if not isinstance(value, str) or not value.strip():
        return f"{field_name} must be a non-empty string"
    if not value.isascii():
        return f"{field_name} must be ASCII"
    for pattern in _FORBIDDEN_CODE_PATTERNS:
        if pattern in value:
            return f"{field_name} contains unsafe characters"
    return None


def _validate_content_type(ct: str) -> bool:
    """Check content type is in the KSO allowlist."""
    if not isinstance(ct, str):
        return False
    return ct.strip().lower() in ALLOWED_CONTENT_TYPES


def _validate_duration_ms(duration: int) -> int:
    """Clamp duration to safe range [1, 86400000]."""
    if not isinstance(duration, (int, float)):
        return 0
    d = int(duration)
    return max(MIN_DURATION_MS, min(d, MAX_DURATION_MS))


def _build_media_ref(slot_order: int) -> str:
    """Build safe mediaRef: media/current/slot-{slotOrder:03d}."""
    order = max(0, slot_order)
    return f"{MEDIA_REF_PREFIX}{order:03d}"


def _validate_manifest_forbidden(result: Dict[str, Any]) -> List[str]:
    """Recursively check manifest dict for forbidden keys/values."""
    hits: List[str] = []

    def _walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                lower_key = key.lower()
                if lower_key in FORBIDDEN_KEYS:
                    hits.append(f"key:{path}.{key}")
                if isinstance(value, str):
                    lower_val = value.lower()
                    for fk in FORBIDDEN_KEYS:
                        if fk in lower_val:
                            hits.append(f"value:{path}.{key}={value[:50]}")
                _walk(value, f"{path}.{key}" if path else key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _walk(item, f"{path}[{i}]")

    _walk(result, "")
    return hits


# ══════════════════════════════════════════════════════════════════════
# Core API
# ══════════════════════════════════════════════════════════════════════

def build_kso_safe_manifest_projection(
    items: List[ManifestSourceItem],
    generated_at: Optional[datetime] = None,
) -> KsoSafeManifestProjectionResult:
    """Build a safe KSO player manifest projection from source items.

    This is a PURE function — no DB, no HTTP, no side effects.
    """
    errors: List[str] = []
    warnings: List[str] = []
    safe_items: List[KsoSafeManifestItem] = []
    excluded = 0

    if not isinstance(items, list):
        return KsoSafeManifestProjectionResult(
            ok=False,
            errors=["items must be a list"],
        )

    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    store_code = ""
    device_code = ""

    for src in items:
        if not isinstance(src, ManifestSourceItem):
            excluded += 1
            warnings.append("Non-ManifestSourceItem in input — skipped")
            continue

        if src.channel_code.strip().lower() != KSO_CHANNEL_CODE:
            excluded += 1
            continue

        if src.campaign_status.strip().lower() != "approved":
            excluded += 1
            continue

        if src.creative_status.strip().lower() != "approved":
            excluded += 1
            continue

        if src.rendition_status.strip().lower() != "valid":
            excluded += 1
            continue

        if src.publication_status.strip().lower() != "published":
            excluded += 1
            continue

        dev_status = src.device_status.strip().lower()
        if dev_status not in ("pending", "active", "lost"):
            excluded += 1
            continue

        if not src.store_is_active:
            excluded += 1
            continue

        if not _validate_content_type(src.content_type):
            excluded += 1
            continue

        now = src.now or generated_at
        if src.valid_to is not None and src.valid_to < now:
            excluded += 1
            continue
        if src.valid_from is not None and src.valid_from > now:
            excluded += 1
            continue

        if not store_code and src.store_code.strip():
            err = _validate_safe_code(src.store_code.strip(), "store_code")
            if err:
                errors.append(err)
                continue
            store_code = src.store_code.strip()
        if not device_code and src.device_code.strip():
            err = _validate_safe_code(src.device_code.strip(), "device_code")
            if err:
                errors.append(err)
                continue
            device_code = src.device_code.strip()

        clamped_duration = _validate_duration_ms(src.duration_ms)
        safe_order = max(0, src.slot_order)

        item = KsoSafeManifestItem(
            slotOrder=safe_order,
            contentType=src.content_type.strip().lower(),
            durationMs=clamped_duration,
            mediaRef=_build_media_ref(safe_order),
            validFrom=src.valid_from.isoformat() if src.valid_from else "",
            validTo=src.valid_to.isoformat() if src.valid_to else "",
        )
        safe_items.append(item)

        if len(safe_items) >= MAX_ITEMS:
            warnings.append(f"Capped at {MAX_ITEMS} items")
            break

    safe_items.sort(key=lambda it: (it.slotOrder, it.contentType))

    for i, item in enumerate(safe_items):
        item.mediaRef = _build_media_ref(i)

    if safe_items and not store_code:
        errors.append("No valid store_code in any item")
    if safe_items and not device_code:
        errors.append("No valid device_code in any item")

    manifest: Dict[str, Any] = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "generatedAt": generated_at.isoformat(),
        "channel": KSO_CHANNEL_CODE,
        "storeCode": store_code,
        "deviceCode": device_code,
        "items": [],
    }

    for item in safe_items:
        manifest["items"].append({
            "slotOrder": item.slotOrder,
            "contentType": item.contentType,
            "durationMs": item.durationMs,
            "mediaRef": item.mediaRef,
            "validFrom": item.validFrom,
            "validTo": item.validTo,
        })

    forbidden_hits = _validate_manifest_forbidden(manifest)
    if forbidden_hits:
        errors.extend(forbidden_hits)

    manifest_bytes = len(json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8"))
    if manifest_bytes > MAX_MANIFEST_BYTES:
        errors.append(
            f"Manifest size {manifest_bytes} exceeds {MAX_MANIFEST_BYTES} bytes"
        )

    ok = len(errors) == 0

    return KsoSafeManifestProjectionResult(
        ok=ok,
        manifest=manifest,
        items_included=len(safe_items),
        items_excluded=excluded,
        errors=errors,
        warnings=warnings,
    )
