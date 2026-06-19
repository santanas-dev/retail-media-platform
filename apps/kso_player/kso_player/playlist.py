"""KSO Player playlist builder — read-only, no backend, no auth, no secret.

Reads only:
  - manifest/current_manifest.json  (local interface contract)
  - media/current/{filename}        (local media cache)

Builds a safe PlayerPlaylist for future player UI integration.
No HTTP, no auth, no secret, no token, no device_code, no backend URL.
"""

import hashlib as _hashlib
import json as _json
import re as _re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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

# ── Local interface contract paths ───────────────────────────────────

_MANIFEST_FILE = "manifest/current_manifest.json"
_MEDIA_CURRENT_DIR = "media/current"


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PlayerPlaylistItem:
    """A single safe playlist item for the player.

    Contains only safe fields. No paths, no secrets, no backend URLs.
    filename is basename-only — never an absolute or relative path.
    """

    manifest_item_id: str       # UUID
    filename: str               # basename only, no path
    content_type: str           # MIME type
    duration_ms: int            # >= 0
    order: int                  # >= 0
    sha256: str                 # 64 hex chars
    size_bytes: Optional[int] = None  # None if unknown


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


# ══════════════════════════════════════════════════════════════════════
# Manifest reader
# ══════════════════════════════════════════════════════════════════════

def _read_manifest(root: Path) -> dict:
    """Read and minimally validate manifest/current_manifest.json.

    Returns parsed dict. Raises FileNotFoundError, ValueError, or
    json.JSONDecodeError on failure.
    """
    path = root / _MANIFEST_FILE

    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    raw = path.read_text(encoding="utf-8")
    data = _json.loads(raw)

    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")

    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("Manifest 'items' must be a list")

    return data


def _extract_item(raw_item: dict, idx: int) -> PlayerPlaylistItem:
    """Extract a safe PlayerPlaylistItem from a raw manifest item dict.

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
        sha256=sha,
        size_bytes=size_bytes,
    )


# ══════════════════════════════════════════════════════════════════════
# Media verifier
# ══════════════════════════════════════════════════════════════════════

def _verify_media_file(root: Path, item: PlayerPlaylistItem) -> bool:
    """Verify a media file exists with correct sha256 and size.

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


# ══════════════════════════════════════════════════════════════════════
# build_playlist
# ══════════════════════════════════════════════════════════════════════

def build_playlist(root) -> PlayerPlaylist:
    """Build a safe playlist from local manifest and media cache.

    Reads only:
      - manifest/current_manifest.json
      - media/current/{filename}

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

    # ── Extract items ────────────────────────────────────────────
    items_total = len(raw_items)
    extracted: list[PlayerPlaylistItem] = []

    for idx, raw in enumerate(raw_items):
        try:
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
    ready_items: list[PlayerPlaylistItem] = []
    items_missing = 0
    items_failed = 0

    for item in extracted:
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
