"""KSO Player playlist builder — read-only, no backend, no auth, no secret.

Reads only:
  - manifest/current_manifest.json  (local interface contract)
  - media/current/{mediaRef}        (KSO safe format — media alias)
  - media/current/{filename}        (legacy format — direct file)

Supports two manifest formats:
  1. KSO Safe Manifest (v1+) — from backend gateway, sidecar-saved
     { schemaVersion, channel, storeCode, deviceCode, items: [{slotOrder, contentType, durationMs, mediaRef, ...}] }
  2. Legacy manifest — demo fixture / test format
     { manifest_id, items: [{manifest_item_id, filename, sha256, content_type, ...}] }

Gateway wrapper detection: if manifest has top-level "status" AND "manifest" keys,
it's a raw gateway response → INVALID for player → hold.

Builds a safe PlayerPlaylist for future player UI integration.
No HTTP, no auth, no secret, no token, no device_code, no backend URL.
"""

import hashlib as _hashlib
import json as _json
import re as _re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

# ── Status / reason ──────────────────────────────────────────────────

REASON_READY = "ready"
REASON_MANIFEST_MISSING = "manifest_missing"
REASON_MANIFEST_INVALID = "manifest_invalid"
REASON_MEDIA_INCOMPLETE = "media_incomplete"
REASON_MEDIA_CORRUPTED = "media_corrupted"
REASON_NO_MEDIA_ITEMS = "no_media_items"

ALLOWED_REASONS = frozenset({
    REASON_READY,
    REASON_MANIFEST_MISSING,
    REASON_MANIFEST_INVALID,
    REASON_MEDIA_INCOMPLETE,
    REASON_MEDIA_CORRUPTED,
    REASON_NO_MEDIA_ITEMS,
})

# ── Forbidden substrings ─────────────────────────────────────────────

FORBIDDEN_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
    "backend_base_url", "127.0.0.1", "device_code",
})

SHA256_RE = _re.compile(r"^[0-9a-fA-F]{64}$")
PATH_TRAVERSAL_RE = _re.compile(r"\.\.|[\\/]|^[A-Za-z]:|^/")

# ── KSO safe manifest constants ──────────────────────────────────────

KSO_CHANNEL = "kso"
KSO_CHANNEL_STRING = "kso"

# Safe mediaRef whitelist: only alphanumeric, slash, underscore, hyphen
# Format: media/current/slot-NNN
_MEDIA_REF_PATTERN = _re.compile(r"^[a-z0-9/_-]+$")

_UNSAFE_IN_MEDIA_REF = frozenset({
    "..", "~", "\\", "://", "file:", "http:", "https:",
    "%2e", "%2f", "%2E", "%2F",
})

# Allowed KSO content types (must match backend)
_ALLOWED_KSO_CONTENT_TYPES = frozenset({
    "image/png", "image/jpeg", "video/mp4",
})

# Gateway wrapper detection keys
_GATEWAY_WRAPPER_KEYS = frozenset({"status", "manifest"})

# ── Local interface contract paths ───────────────────────────────────

_MANIFEST_FILE = "manifest/current_manifest.json"
_MEDIA_CURRENT_DIR = "media/current"


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PlayerPlaylistItem:
    """A single safe playlist item for the player.

    KSO safe format (v1+): media_ref + content_type + duration_ms + slot_order.
    Legacy format: manifest_item_id + filename + sha256 + content_type + order.

    Contains only safe fields. No paths, no secrets, no backend URLs.
    media_ref is a relative alias like "media/current/slot-000".
    filename is basename-only — never an absolute or relative path.
    """

    # KSO safe format fields
    media_ref: str = ""           # relative alias: "media/current/slot-000"
    slot_order: int = 0           # slot position in sequence

    # Legacy format fields
    manifest_item_id: str = ""    # UUID (LEGACY — not present in safe format)
    filename: str = ""            # basename only, no path (LEGACY)
    sha256: str = ""              # 64 hex chars (LEGACY)

    # Common fields (both formats)
    content_type: str = ""        # MIME type
    duration_ms: int = 0          # >= 0
    order: int = 0                # >= 0 (LEGACY alias for slot_order)
    size_bytes: Optional[int] = None  # None if unknown (LEGACY)

    # — Backend creative identity —
    creative_code: Optional[str] = None  # safe code from manifest, None if unavailable


@dataclass
class PlayerPlaylist:
    """Safe playlist built from local manifest + media cache.

    ready=True only when manifest is valid AND all media files pass verification.
    items contains only verified-ready items (never incomplete/corrupted).
    """

    ready: bool = False
    status: str = "not_ready"   # "ready" | "not_ready" | "error"
    reason: str = REASON_MANIFEST_MISSING
    items_total: int = 0
    items_ready: int = 0
    items_missing: int = 0
    items_failed: int = 0
    items: list = field(default_factory=list)  # list[PlayerPlaylistItem]


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _compute_sha256(filepath: Path) -> str:
    """Compute sha256 of a file (streaming)."""
    sha = _hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _check_forbidden(value: str, field: str) -> None:
    """Raise ValueError if value contains any forbidden substring."""
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise ValueError(
                f"Field '{field}' contains forbidden substring '{fb}'"
            )


def _validate_filename(filename: str, field: str) -> str:
    """Validate filename is safe — basename only, no path, no forbidden."""
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError(f"{field}: must be a non-empty string")
    if PATH_TRAVERSAL_RE.search(filename):
        raise ValueError(
            f"{field}: path traversal not allowed in '{filename}'"
        )
    _check_forbidden(filename, field)
    return filename


def _validate_media_ref(media_ref: str, field: str) -> str:
    """Validate mediaRef is a safe relative alias (^[a-z0-9/_-]+$).

    Must NOT start with / (absolute path) or contain path traversal.
    """
    if not isinstance(media_ref, str) or not media_ref.strip():
        raise ValueError(f"{field}: must be a non-empty string")
    if media_ref.startswith("/"):
        raise ValueError(
            f"{field}: absolute path not allowed, got '{media_ref}'"
        )
    if not _MEDIA_REF_PATTERN.match(media_ref):
        raise ValueError(
            f"{field}: must match pattern ^[a-z0-9/_-]+$, got '{media_ref}'"
        )
    lower = media_ref.lower()
    for unsafe in _UNSAFE_IN_MEDIA_REF:
        if unsafe in lower:
            raise ValueError(
                f"{field}: contains unsafe pattern '{unsafe}'"
            )
    _check_forbidden(media_ref, field)
    return media_ref


def _validate_content_type(ct: str) -> bool:
    """Check content type is allowed for KSO player."""
    if not isinstance(ct, str):
        return False
    return ct.strip().lower() in _ALLOWED_KSO_CONTENT_TYPES


# ══════════════════════════════════════════════════════════════════════
# Format detection
# ══════════════════════════════════════════════════════════════════════

def _is_gateway_wrapper(data: dict) -> bool:
    """Detect if manifest is a raw gateway response wrapper.

    Gateway responses look like:
      { "status": "served", "manifest_version_id": "...", "manifest": {...} }

    The player must NEVER receive a wrapper — sidecar should strip it.
    If player gets a wrapper, treat as invalid → hold.
    """
    if not isinstance(data, dict):
        return False
    keys = {k.lower() for k in data}
    return "status" in keys and "manifest" in keys


def _is_kso_safe_format(data: dict) -> bool:
    """Detect if manifest uses KSO safe format (v1+ from backend).

    Safe format has: schemaVersion, channel=kso, items[].mediaRef.
    Legacy format has: manifest_id, items[].manifest_item_id, items[].filename.
    """
    if not isinstance(data, dict):
        return False

    # Check for safe format markers
    items = data.get("items")
    if not isinstance(items, list) or len(items) == 0:
        # Empty items — could be either, check channel
        channel = data.get("channel", "")
        if isinstance(channel, str) and channel.lower() == KSO_CHANNEL:
            return True
        return False

    first_item = items[0]
    if not isinstance(first_item, dict):
        return False

    # Safe format: items have "mediaRef"
    # Legacy format: items have "filename" and "manifest_item_id"
    has_media_ref = "mediaRef" in first_item
    has_filename = "filename" in first_item or "manifest_item_id" in first_item

    if has_media_ref and not has_filename:
        return True
    if has_filename and not has_media_ref:
        return False

    # Ambiguous — use channel field as tiebreaker
    channel = data.get("channel", "")
    if isinstance(channel, str) and channel.lower() == KSO_CHANNEL:
        return True

    return False


# ══════════════════════════════════════════════════════════════════════
# Manifest reader
# ══════════════════════════════════════════════════════════════════════

def _read_manifest(root: Path) -> dict:
    """Read and minimally validate manifest/current_manifest.json.

    Returns parsed dict. Raises FileNotFoundError, ValueError, or
    json.JSONDecodeError on failure.
    Also rejects gateway wrapper manifests.
    """
    path = root / _MANIFEST_FILE

    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    raw = path.read_text(encoding="utf-8")
    data = _json.loads(raw)

    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")

    # ── Gateway wrapper detection ────────────────────────────────
    # Player must ONLY receive the safe manifest body, never the wrapper.
    # If wrapper is detected → invalid → hold.
    if _is_gateway_wrapper(data):
        raise ValueError(
            "Gateway wrapper manifest — player must receive only safe manifest body"
        )

    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("Manifest 'items' must be a list")

    return data


# ══════════════════════════════════════════════════════════════════════
# Legacy extractors (backward compatible)
# ══════════════════════════════════════════════════════════════════════

def _extract_item(raw_item: dict, idx: int) -> PlayerPlaylistItem:
    """Extract a safe PlayerPlaylistItem from a raw LEGACY manifest item dict.

    Validates all fields. Rejects items with forbidden substrings,
    path traversal in filename, or invalid data.
    """
    if not isinstance(raw_item, dict):
        raise ValueError(
            f"items[{idx}]: expected object, got {type(raw_item).__name__}"
        )

    # manifest_item_id — must be present and non-empty
    mid = raw_item.get("manifest_item_id", "")
    if not isinstance(mid, str) or not mid.strip():
        raise ValueError(f"items[{idx}].manifest_item_id: required non-empty string")

    # filename — basename only
    filename = _validate_filename(
        raw_item.get("filename", ""), f"items[{idx}].filename"
    )

    # content_type
    ct = raw_item.get("content_type", "")
    if not isinstance(ct, str) or not ct.strip():
        raise ValueError(f"items[{idx}].content_type: required non-empty string")

    # sha256
    sha = raw_item.get("sha256", "")
    if not isinstance(sha, str) or not SHA256_RE.match(sha):
        raise ValueError(f"items[{idx}].sha256: must be 64 hex chars")

    # duration_ms
    dur = raw_item.get("duration_ms", 0)
    if not isinstance(dur, int) or dur < 0:
        raise ValueError(
            f"items[{idx}].duration_ms: must be >= 0, got {dur!r}"
        )

    # order
    order = raw_item.get("order", 0)
    if not isinstance(order, int) or order < 0:
        raise ValueError(
            f"items[{idx}].order: must be >= 0, got {order!r}"
        )

    # size_bytes — may be 0 (unknown) or None
    sb = raw_item.get("size_bytes", 0)
    if sb is None:
        size_bytes = None
    elif isinstance(sb, int) and sb >= 0:
        size_bytes = sb if sb > 0 else None
    else:
        raise ValueError(
            f"items[{idx}].size_bytes: must be int >= 0 or null, got {sb!r}"
        )

    return PlayerPlaylistItem(
        manifest_item_id=mid,
        filename=filename,
        content_type=ct,
        duration_ms=dur,
        order=order,
        slot_order=order,
        sha256=sha,
        size_bytes=size_bytes,
    )


# ══════════════════════════════════════════════════════════════════════
# KSO safe format extractors
# ══════════════════════════════════════════════════════════════════════

def _extract_kso_item(raw_item: dict, idx: int) -> PlayerPlaylistItem:
    """Extract a safe PlayerPlaylistItem from a KSO safe manifest item.

    Expected fields: slotOrder, contentType, durationMs, mediaRef.
    Optional: validFrom, validTo (ignored by player).

    Rejects: invalid types, unsafe mediaRef, unsupported contentType,
    forbidden substrings.
    """
    if not isinstance(raw_item, dict):
        raise ValueError(
            f"items[{idx}]: expected object, got {type(raw_item).__name__}"
        )

    # ── slotOrder ────────────────────────────────────────────────
    slot_order = raw_item.get("slotOrder")
    if not isinstance(slot_order, int) or slot_order < 0:
        raise ValueError(
            f"items[{idx}].slotOrder: must be int >= 0, got {slot_order!r}"
        )

    # ── contentType ──────────────────────────────────────────────
    ct = raw_item.get("contentType", "")
    if not isinstance(ct, str) or not ct.strip():
        raise ValueError(f"items[{idx}].contentType: required non-empty string")
    ct = ct.strip().lower()
    if not _validate_content_type(ct):
        raise ValueError(
            f"items[{idx}].contentType: unsupported MIME type '{ct}'"
        )

    # ── durationMs ───────────────────────────────────────────────
    dur = raw_item.get("durationMs", 0)
    if not isinstance(dur, int) or dur < 0:
        raise ValueError(
            f"items[{idx}].durationMs: must be int >= 0, got {dur!r}"
        )

    # ── mediaRef ─────────────────────────────────────────────────
    media_ref = raw_item.get("mediaRef", "")
    media_ref = _validate_media_ref(media_ref, f"items[{idx}].mediaRef")

    # ── creativeCode (optional — safe identifier from backend) ───
    creative_code = raw_item.get("creativeCode")
    if creative_code is not None:
        if not isinstance(creative_code, str) or not creative_code.strip():
            creative_code = None  # reject empty/non-string
        else:
            creative_code = creative_code.strip()
            _check_forbidden(creative_code, f"items[{idx}].creativeCode")

    # ── Check forbidden substrings on all string fields ──────────
    _check_forbidden(ct, f"items[{idx}].contentType")
    _check_forbidden(media_ref, f"items[{idx}].mediaRef")

    return PlayerPlaylistItem(
        media_ref=media_ref,
        slot_order=slot_order,
        content_type=ct,
        duration_ms=dur,
        order=slot_order,  # alias for compatibility
        creative_code=creative_code,
    )


# ══════════════════════════════════════════════════════════════════════
# Media verifiers
# ══════════════════════════════════════════════════════════════════════

def _verify_media_file(root: Path, item: PlayerPlaylistItem) -> bool:
    """Verify a media file exists with correct sha256 and size (LEGACY format).

    Returns True if the file is present, valid, and NOT a symlink.
    Returns False if missing, symlink, sha256 mismatch, size mismatch, or unreadable.
    """
    filepath = root / _MEDIA_CURRENT_DIR / item.filename

    if not filepath.exists() or not filepath.is_file():
        return False

    # Reject symlinks
    if filepath.is_symlink():
        return False

    try:
        actual_sha = _compute_sha256(filepath)
        if actual_sha != item.sha256:
            return False
    except Exception:
        return False

    if item.size_bytes is not None and item.size_bytes > 0:
        try:
            actual_size = filepath.stat().st_size
            if actual_size != item.size_bytes:
                return False
        except OSError:
            return False

    return True


def _verify_kso_media(root: Path, item: PlayerPlaylistItem) -> bool:
    """Verify KSO safe media: check that mediaRef target exists.

    KSO safe format has no sha256 in manifest — verification is
    existence-only. Symlinks ARE allowed (media aliases in demo).

    Returns True if the file or symlink at {root}/{media_ref} exists.
    """
    # media_ref is already validated by _extract_kso_item
    target = root / item.media_ref

    # Allow symlinks — media aliases in demo are symlinks
    return target.exists() and (target.is_file() or target.is_symlink())


# ══════════════════════════════════════════════════════════════════════
# build_playlist
# ══════════════════════════════════════════════════════════════════════

def build_playlist(root) -> PlayerPlaylist:
    """Build a safe playlist from local manifest and media cache.

    Supports two manifest formats:
      - KSO Safe Manifest (v1+): schemaVersion, channel=kso, items[].mediaRef
      - Legacy manifest: manifest_id, items[].filename, items[].sha256

    Reads only:
      - manifest/current_manifest.json
      - media/current/{filename}    (legacy)
      - {mediaRef}                  (KSO safe — relative alias)

    No backend, no HTTP, no auth, no secret, no token.
    Never returns absolute paths, media_path, creatives/, or backend URLs.

    Args:
        root: Agent root path (str or Path).

    Returns:
        PlayerPlaylist — always returns a result, never raises exceptions.
        Errors are captured in status/reason fields.
    """
    root = Path(root)

    # ── Read manifest ────────────────────────────────────────────
    try:
        manifest = _read_manifest(root)
    except FileNotFoundError:
        return PlayerPlaylist(
            ready=False, status="not_ready",
            reason=REASON_MANIFEST_MISSING,
        )
    except (_json.JSONDecodeError, ValueError):
        return PlayerPlaylist(
            ready=False, status="error",
            reason=REASON_MANIFEST_INVALID,
        )

    raw_items = manifest.get("items", [])

    if len(raw_items) == 0:
        return PlayerPlaylist(
            ready=False, status="not_ready",
            reason=REASON_NO_MEDIA_ITEMS,
            items_total=0,
        )

    # ── Detect format ────────────────────────────────────────────
    use_kso_format = _is_kso_safe_format(manifest)

    # ── Channel check for KSO ────────────────────────────────────
    if use_kso_format:
        channel = manifest.get("channel", "")
        if isinstance(channel, str) and channel.lower() != KSO_CHANNEL:
            # Non-KSO channel in safe format → reject all items
            return PlayerPlaylist(
                ready=False, status="error",
                reason=REASON_MANIFEST_INVALID,
                items_total=len(raw_items),
            )

    # ── Extract items ────────────────────────────────────────────
    items_total = len(raw_items)
    extracted: List[PlayerPlaylistItem] = []

    for idx, raw in enumerate(raw_items):
        try:
            if use_kso_format:
                item = _extract_kso_item(raw, idx)
            else:
                item = _extract_item(raw, idx)
            extracted.append(item)
        except (ValueError, KeyError, TypeError):
            # Invalid item — skip it (don't include in playlist)
            continue

    if not extracted:
        # All items failed extraction → invalid manifest
        return PlayerPlaylist(
            ready=False, status="error",
            reason=REASON_MANIFEST_INVALID,
            items_total=items_total,
        )

    # ── Verify media files ───────────────────────────────────────
    ready_items: List[PlayerPlaylistItem] = []
    items_missing = 0
    items_failed = 0

    for item in extracted:
        if use_kso_format:
            if _verify_kso_media(root, item):
                ready_items.append(item)
            else:
                items_missing += 1
        else:
            if _verify_media_file(root, item):
                ready_items.append(item)
            else:
                filepath = root / _MEDIA_CURRENT_DIR / item.filename
                if not filepath.exists():
                    items_missing += 1
                else:
                    items_failed += 1

    items_ready = len(ready_items)
    items_missing_count = items_missing
    items_failed_count = items_failed

    # ── Determine status ─────────────────────────────────────────
    if items_failed_count > 0:
        return PlayerPlaylist(
            ready=False, status="error",
            reason=REASON_MEDIA_CORRUPTED,
            items_total=items_total,
            items_ready=items_ready,
            items_missing=items_missing_count,
            items_failed=items_failed_count,
            items=ready_items,
        )

    if items_missing_count > 0:
        return PlayerPlaylist(
            ready=False, status="not_ready",
            reason=REASON_MEDIA_INCOMPLETE,
            items_total=items_total,
            items_ready=items_ready,
            items_missing=items_missing_count,
            items_failed=0,
            items=ready_items,
        )

    # All items ready
    return PlayerPlaylist(
        ready=True, status="ready",
        reason=REASON_READY,
        items_total=items_total,
        items_ready=items_ready,
        items_missing=0,
        items_failed=0,
        items=ready_items,
    )
