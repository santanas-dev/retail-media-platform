"""KSO Sidecar — Safe Gateway Manifest Extractor.

Takes a backend gateway response:
  {
    "status": "served",
    "manifest_version_id": "<uuid>",
    "manifest_hash": "<sha256>",
    "published_at": "ISO8601",
    "manifest": {
      "schemaVersion": 1,
      "channel": "kso",
      "storeCode": "safe_code",
      "deviceCode": "safe_code",
      "items": [{ "slotOrder": 0, "contentType": "image/png", ... }]
    }
  }

Extracts ONLY response["manifest"] as the KSO safe manifest body.
Validates it, then writes atomically to manifest/current_manifest.json
for the KSO Player to consume.

This is NOT an HTTP client, NOT a media downloader, NOT PoP.
Pure extraction + validation + atomic write.
"""

import json
import re as _re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from kso_sidecar_agent.atomic_io import atomic_write_json
from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

KSO_CHANNEL = "kso"
MANIFEST_SCHEMA_VERSION = 1

# Allowed MIME types for KSO v1
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset({
    "image/png", "image/jpeg", "video/mp4",
})

# Safe mediaRef whitelist
_MEDIA_REF_PATTERN = _re.compile(r"^[a-z0-9/_-]+$")
_MEDIA_REF_PREFIX = "media/current/slot-"

_UNSAFE_IN_MEDIA_REF = frozenset({
    "..", "~", "\\", "://", "file:", "http:", "https:",
    "%2e", "%2f", "%2E", "%2F",
})

# Forbidden keys — MUST NOT appear in player manifest body
FORBIDDEN_MANIFEST_KEYS: frozenset[str] = frozenset({
    "status", "manifest_version_id", "manifest_hash", "published_at",
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token", "cookie",
    "backend_base_url", "127.0.0.1", "device_code",
    "manifest_item_id", "campaign_id", "creative_id",
    "rendition_id", "schedule_item_id", "batch_id", "booking_id",
    "file_path", "media_path", "creatives/",
    "minio", "s3://", "bucket",
    "budget", "currency", "price",
    "customer_id", "phone", "email", "receipt_data",
    "card_number", "pan", "fiscal_data",
    "sha256", "filename",
})

# Forbidden in store/device codes
_FORBIDDEN_CODE_PATTERNS = frozenset({"..", "/", "\\", " "})

# Result statuses
STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_NOT_MODIFIED = "not_modified"
STATUS_NO_MANIFEST = "no_manifest"

REASON_SERVED = "served"
REASON_NOT_MODIFIED = "not_modified"
REASON_NO_MANIFEST = "no_manifest"
REASON_INVALID_RESPONSE = "invalid_gateway_response"
REASON_NON_KSO_CHANNEL = "non_kso_channel"
REASON_UNSAFE_MANIFEST = "unsafe_manifest_body"
REASON_WRITE_FAILED = "write_failed"
REASON_INVALID_ARGS = "invalid_args"


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoGatewayManifestExtractionResult:
    """Safe result of extracting KSO safe manifest from gateway response.

    NEVER contains: paths, filenames, mediaRef values, IDs, raw JSON,
    manifest_version_id, manifest_hash, exception text.
    """

    status: str = STATUS_ERROR
    extracted: bool = False
    reason: str = REASON_INVALID_ARGS
    items_count: int = 0
    channel: str = ""
    store_code_present: bool = False
    device_code_present: bool = False

    # Internal — NEVER exposed in repr/format/output
    _manifest_body: Dict[str, Any] = field(default_factory=dict, repr=False)
    _errors: List[str] = field(default_factory=list, repr=False)

    def __repr__(self) -> str:
        return (
            f"KsoGatewayManifestExtractionResult("
            f"status={self.status!r}, "
            f"extracted={self.extracted}, "
            f"reason={self.reason!r}, "
            f"items_count={self.items_count}, "
            f"channel={self.channel!r}, "
            f"store_code_present={self.store_code_present}, "
            f"device_code_present={self.device_code_present})"
        )


@dataclass
class KsoGatewayManifestWriteResult:
    """Safe result of writing KSO safe manifest locally.

    NEVER contains: paths, filenames, mediaRef values, IDs, raw JSON,
    manifest_version_id, manifest_hash, exception text.
    """

    status: str = STATUS_ERROR
    written: bool = False
    manifest_ready: bool = False
    items_count: int = 0
    reason: str = REASON_INVALID_ARGS
    extraction_status: str = STATUS_ERROR

    def __repr__(self) -> str:
        return (
            f"KsoGatewayManifestWriteResult("
            f"status={self.status!r}, "
            f"written={self.written}, "
            f"manifest_ready={self.manifest_ready}, "
            f"items_count={self.items_count}, "
            f"reason={self.reason!r}, "
            f"extraction_status={self.extraction_status!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers — validation
# ══════════════════════════════════════════════════════════════════════

def _validate_safe_code(value: str, field_name: str) -> Optional[str]:
    """Validate a store/device code is safe: ^[a-z0-9_-]+$ without path traversal."""
    if not isinstance(value, str) or not value.strip():
        return f"{field_name}: must be a non-empty string"
    if not value.isascii():
        return f"{field_name}: must be ASCII"
    for pattern in _FORBIDDEN_CODE_PATTERNS:
        if pattern in value:
            return f"{field_name}: contains unsafe characters"
    return None


def _validate_media_ref(media_ref: str) -> Optional[str]:
    """Validate mediaRef is safe. Returns error string or None."""
    if not isinstance(media_ref, str) or not media_ref.strip():
        return "mediaRef: must be a non-empty string"
    if media_ref.startswith("/"):
        return f"mediaRef: absolute path not allowed"
    if not _MEDIA_REF_PATTERN.match(media_ref):
        return f"mediaRef: must match ^[a-z0-9/_-]+$"
    if not media_ref.startswith(_MEDIA_REF_PREFIX):
        return f"mediaRef: must start with 'media/current/slot-'"
    lower = media_ref.lower()
    for unsafe in _UNSAFE_IN_MEDIA_REF:
        if unsafe in lower:
            return f"mediaRef: contains unsafe pattern '{unsafe}'"
    return None


def _validate_content_type(ct: str) -> bool:
    """Check content type is in KSO allowlist."""
    if not isinstance(ct, str):
        return False
    return ct.strip().lower() in ALLOWED_CONTENT_TYPES


def _check_forbidden_keys(manifest: Dict[str, Any]) -> List[str]:
    """Recursively check manifest dict for forbidden keys. Returns list of hits."""
    hits: List[str] = []

    def _walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                lower_key = key.lower()
                if lower_key in FORBIDDEN_MANIFEST_KEYS:
                    hits.append(f"forbidden_key:{path}.{key}")
                if isinstance(value, str):
                    lower_val = value.lower()
                    for fk in FORBIDDEN_MANIFEST_KEYS:
                        if fk in lower_val:
                            hits.append(f"forbidden_value:{path}.{key}")
                _walk(value, f"{path}.{key}" if path else key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _walk(item, f"{path}[{i}]")

    _walk(manifest, "")
    return hits


# ══════════════════════════════════════════════════════════════════════
# Helpers — item validation
# ══════════════════════════════════════════════════════════════════════

def _validate_kso_item(item: dict, idx: int, errors: List[str]) -> bool:
    """Validate one KSO safe manifest item. Returns True if valid.

    Expected fields: slotOrder, contentType, durationMs, mediaRef.
    Optional: validFrom, validTo.
    """
    if not isinstance(item, dict):
        errors.append(f"items[{idx}]: expected object, got {type(item).__name__}")
        return False

    ok = True

    # slotOrder — must be non-negative int
    slot_order = item.get("slotOrder")
    if not isinstance(slot_order, int) or slot_order < 0:
        errors.append(f"items[{idx}].slotOrder: must be int >= 0, got {slot_order!r}")
        ok = False

    # contentType — must be in allowlist
    ct = item.get("contentType", "")
    if not isinstance(ct, str) or not ct.strip():
        errors.append(f"items[{idx}].contentType: must be non-empty string")
        ok = False
    elif not _validate_content_type(ct):
        errors.append(f"items[{idx}].contentType: unsupported '{ct}'")
        ok = False

    # durationMs — must be non-negative int
    dur = item.get("durationMs", 0)
    if not isinstance(dur, int) or dur < 0:
        errors.append(f"items[{idx}].durationMs: must be int >= 0, got {dur!r}")
        ok = False

    # mediaRef — must be safe
    media_ref = item.get("mediaRef", "")
    if not isinstance(media_ref, str):
        errors.append(f"items[{idx}].mediaRef: must be string, got {type(media_ref).__name__}")
        ok = False
    else:
        ref_error = _validate_media_ref(media_ref)
        if ref_error:
            errors.append(f"items[{idx}].{ref_error}")
            ok = False

    # validFrom (optional) — must be ISO-like string if present
    vf = item.get("validFrom")
    if vf is not None:
        if not isinstance(vf, str):
            errors.append(f"items[{idx}].validFrom: must be string or absent")
            ok = False

    # validTo (optional) — must be ISO-like string if present
    vt = item.get("validTo")
    if vt is not None:
        if not isinstance(vt, str):
            errors.append(f"items[{idx}].validTo: must be string or absent")
            ok = False

    return ok


# ══════════════════════════════════════════════════════════════════════
# Extractor
# ══════════════════════════════════════════════════════════════════════

def extract_kso_safe_manifest_body_from_gateway_response(
    response: Mapping[str, Any],
) -> KsoGatewayManifestExtractionResult:
    """Extract KSO safe manifest body from a backend gateway response.

    Handles:
      - status="served" + manifest body → extract and validate
      - status="not_modified" → skip (nothing to extract)
      - status="no_manifest" → skip
      - invalid/missing → safe error

    Args:
        response: Gateway response dict (from HTTP JSON).

    Returns:
        KsoGatewayManifestExtractionResult — safe aggregate, never raises.
    """
    errors: List[str] = []

    # ── Validate response is a mapping ────────────────────────────
    if not isinstance(response, Mapping):
        return KsoGatewayManifestExtractionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESPONSE,
            _errors=["response must be a dict/mapping"],
        )

    # ── Check status ──────────────────────────────────────────────
    status = response.get("status", "")
    if not isinstance(status, str) or not status.strip():
        return KsoGatewayManifestExtractionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESPONSE,
            _errors=["response missing 'status' field"],
        )

    # ── Handle not_modified and no_manifest ───────────────────────
    if status == "not_modified":
        return KsoGatewayManifestExtractionResult(
            status=STATUS_NOT_MODIFIED,
            reason=REASON_NOT_MODIFIED,
        )

    if status == "no_manifest":
        return KsoGatewayManifestExtractionResult(
            status=STATUS_NO_MANIFEST,
            reason=REASON_NO_MANIFEST,
        )

    if status != "served":
        return KsoGatewayManifestExtractionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESPONSE,
            _errors=[f"unexpected status: '{status}'"],
        )

    # ── Extract manifest body ─────────────────────────────────────
    manifest = response.get("manifest")
    if not isinstance(manifest, Mapping):
        return KsoGatewayManifestExtractionResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_RESPONSE,
            _errors=["response['manifest'] missing or not a dict"],
        )

    # Convert to plain dict (from Mapping)
    manifest_body = dict(manifest)

    # ── Validate top-level fields ─────────────────────────────────

    # schemaVersion
    sv = manifest_body.get("schemaVersion")
    if sv != MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"schemaVersion: expected {MANIFEST_SCHEMA_VERSION}, got {sv!r}"
        )

    # channel
    channel = manifest_body.get("channel", "")
    if not isinstance(channel, str) or channel.lower() != KSO_CHANNEL:
        errors.append(f"channel: must be '{KSO_CHANNEL}', got {channel!r}")

    # storeCode
    store_code = manifest_body.get("storeCode", "")
    store_code_err = _validate_safe_code(store_code, "storeCode")
    if store_code_err:
        errors.append(store_code_err)

    # deviceCode
    device_code = manifest_body.get("deviceCode", "")
    device_code_err = _validate_safe_code(device_code, "deviceCode")
    if device_code_err:
        errors.append(device_code_err)

    # items
    items = manifest_body.get("items")
    if not isinstance(items, list):
        errors.append("items: must be a list")
        items = []

    # ── Validate each item ────────────────────────────────────────
    valid_items = 0
    for idx, item in enumerate(items):
        if _validate_kso_item(item, idx, errors):
            valid_items += 1

    # ── Forbidden keys check ──────────────────────────────────────
    forbidden_hits = _check_forbidden_keys(manifest_body)
    errors.extend(forbidden_hits)

    # ── Determine result ──────────────────────────────────────────
    if errors:
        return KsoGatewayManifestExtractionResult(
            status=STATUS_ERROR,
            reason=REASON_UNSAFE_MANIFEST,
            items_count=valid_items,
            channel=channel if isinstance(channel, str) else "",
            store_code_present=bool(store_code and isinstance(store_code, str) and store_code.strip()),
            device_code_present=bool(device_code and isinstance(device_code, str) and device_code.strip()),
            _manifest_body={},
            _errors=errors,
        )

    if channel.lower() != KSO_CHANNEL:
        return KsoGatewayManifestExtractionResult(
            status=STATUS_ERROR,
            reason=REASON_NON_KSO_CHANNEL,
            channel=channel if isinstance(channel, str) else "",
        )

    return KsoGatewayManifestExtractionResult(
        status=STATUS_OK,
        extracted=True,
        reason=REASON_SERVED,
        items_count=len(items),
        channel=KSO_CHANNEL,
        store_code_present=True,
        device_code_present=True,
        _manifest_body=manifest_body,
    )


# ══════════════════════════════════════════════════════════════════════
# Writer
# ══════════════════════════════════════════════════════════════════════

def write_kso_safe_local_manifest_from_gateway_response(
    root,
    response: Mapping[str, Any],
) -> KsoGatewayManifestWriteResult:
    """Extract KSO safe manifest from gateway response and write atomically.

    Writes ONLY response["manifest"] to {root}/manifest/current_manifest.json.
    Uses atomic write (tmp + replace).

    Args:
        root: Agent root path (str or Path).
        response: Gateway response dict.

    Returns:
        KsoGatewayManifestWriteResult — safe aggregate, never raises.
    """
    # ── Validate root ─────────────────────────────────────────────
    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoGatewayManifestWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    # ── Extract ───────────────────────────────────────────────────
    try:
        extraction = extract_kso_safe_manifest_body_from_gateway_response(response)
    except Exception:
        return KsoGatewayManifestWriteResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
            extraction_status=STATUS_ERROR,
        )

    # ── Handle non-served statuses ────────────────────────────────
    if extraction.status == STATUS_NOT_MODIFIED:
        return KsoGatewayManifestWriteResult(
            status=STATUS_NOT_MODIFIED,
            written=False,
            manifest_ready=False,
            items_count=0,
            reason=REASON_NOT_MODIFIED,
            extraction_status=STATUS_NOT_MODIFIED,
        )

    if extraction.status == STATUS_NO_MANIFEST:
        return KsoGatewayManifestWriteResult(
            status=STATUS_NO_MANIFEST,
            written=False,
            manifest_ready=False,
            items_count=0,
            reason=REASON_NO_MANIFEST,
            extraction_status=STATUS_NO_MANIFEST,
        )

    if not extraction.extracted:
        return KsoGatewayManifestWriteResult(
            status=STATUS_ERROR,
            written=False,
            manifest_ready=False,
            items_count=extraction.items_count,
            reason=extraction.reason,
            extraction_status=extraction.status,
        )

    # ── Atomic write ──────────────────────────────────────────────
    manifest_body = extraction._manifest_body
    target = root / CURRENT_MANIFEST_FILE

    # Ensure parent directory exists
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        atomic_write_json(target, manifest_body)
    except Exception:
        return KsoGatewayManifestWriteResult(
            status=STATUS_ERROR,
            reason=REASON_WRITE_FAILED,
            extraction_status=STATUS_OK,
            items_count=extraction.items_count,
        )

    return KsoGatewayManifestWriteResult(
        status=STATUS_OK,
        written=True,
        manifest_ready=True,
        items_count=extraction.items_count,
        reason=REASON_SERVED,
        extraction_status=STATUS_OK,
    )


# ══════════════════════════════════════════════════════════════════════
# Formatters
# ══════════════════════════════════════════════════════════════════════

def format_extraction_result(
    result: KsoGatewayManifestExtractionResult,
) -> str:
    """Format extraction result as safe human-readable string.

    NEVER contains paths, filenames, mediaRef values, IDs, raw JSON.
    """
    lines = [
        f"status: {result.status}",
        f"extracted: {str(result.extracted).lower()}",
        f"reason: {result.reason}",
        f"items_count: {result.items_count}",
        f"channel: {result.channel if result.channel else '(none)'}",
    ]
    return "\n".join(lines)


def format_write_result(
    result: KsoGatewayManifestWriteResult,
) -> str:
    """Format write result as safe human-readable string.

    NEVER contains paths, filenames, mediaRef values, IDs, raw JSON.
    """
    lines = [
        f"status: {result.status}",
        f"written: {str(result.written).lower()}",
        f"manifest_ready: {str(result.manifest_ready).lower()}",
        f"items_count: {result.items_count}",
        f"reason: {result.reason}",
    ]
    return "\n".join(lines)
