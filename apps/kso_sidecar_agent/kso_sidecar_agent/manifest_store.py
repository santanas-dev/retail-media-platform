"""Manifest Local Store for KSO Sidecar Agent.

Normalizes backend ManifestSnapshot → local manifest/current_manifest.json.
Atomic write, validation, security scan. No backend calls, no secrets.

Compatible with:
  - docs/kso_local_interface_contract.md
  - tools/kso_simulator/kso_simulator/manifest_reader.py
"""

import json
import os
import re as _re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID as _UUID

from kso_sidecar_agent.atomic_io import atomic_write_json
from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
})

SHA256_RE = _re.compile(r"^[0-9a-fA-F]{64}$")
PATH_TRAVERSAL_RE = _re.compile(r"\.\.|[\\]|^[A-Za-z]:|^/")

# Extension → MIME type
EXT_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}

# Reverse: MIME → extension
MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
}


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden(value: str, field_path: str) -> None:
    """Raise ValueError if value contains any forbidden substring."""
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise ValueError(
                f"Local manifest field '{field_path}' contains forbidden substring '{fb}'"
            )


def _validate_filename(filename: str, field_path: str) -> str:
    """Validate filename is safe (no path traversal, no slashes)."""
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError(f"{field_path}: must be a non-empty string")
    if PATH_TRAVERSAL_RE.search(filename):
        raise ValueError(
            f"{field_path}: path traversal not allowed in filename '{filename}'"
        )
    return filename


def _derive_content_type(media_path: Optional[str]) -> str:
    """Derive content_type from media_path extension. Returns 'application/octet-stream' if unknown."""
    if not isinstance(media_path, str) or not media_path:
        return "application/octet-stream"
    # Check no path traversal
    if PATH_TRAVERSAL_RE.search(media_path):
        raise ValueError(
            f"Cannot derive content_type from unsafe media_path: '{media_path}'"
        )
    ext = os.path.splitext(media_path)[1].lower()
    return EXT_TO_MIME.get(ext, "application/octet-stream")


def _derive_filename(manifest_item_id: str, content_type: str) -> str:
    """Derive safe filename from manifest_item_id + extension."""
    ext = MIME_TO_EXT.get(content_type, ".bin")
    return f"{manifest_item_id}{ext}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════
# Security scan
# ══════════════════════════════════════════════════════════════════════

def _security_scan(data: dict, path: str = "$") -> None:
    """Recursively check all keys and string values for forbidden substrings."""
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        full_path = f"{path}.{key}" if path else key
        _check_forbidden(key, f"key '{full_path}'")
        if isinstance(value, str):
            _check_forbidden(value, f"value '{full_path}'")
        elif isinstance(value, dict):
            _security_scan(value, full_path)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    _security_scan(item, f"{full_path}[{i}]")
                elif isinstance(item, str):
                    _check_forbidden(item, f"value '{full_path}[{i}]'")


# ══════════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════════

def _validate_uuid(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected string, got {type(value).__name__}")
    try:
        _UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"{field}: '{value}' is not a valid UUID")
    return value


def _validate_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.match(value):
        raise ValueError(f"{field}: must be 64 hex chars")
    return value


def _validate_non_negative(value: Any, field: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field}: must be >= 0, got {value!r}")
    return value


def _validate_item(item: dict, idx: int) -> dict:
    """Validate a single local manifest item. Returns validated copy."""
    if not isinstance(item, dict):
        raise ValueError(f"items[{idx}]: expected object, got {type(item).__name__}")

    validated: dict = {}
    validated["manifest_item_id"] = _validate_uuid(
        item.get("manifest_item_id"), f"items[{idx}].manifest_item_id"
    )
    validated["filename"] = _validate_filename(
        item.get("filename", ""), f"items[{idx}].filename"
    )
    ct = item.get("content_type", "")
    if not isinstance(ct, str) or not ct.strip():
        raise ValueError(f"items[{idx}].content_type: must be a non-empty string")
    validated["content_type"] = ct
    validated["sha256"] = _validate_sha256(
        item.get("sha256", ""), f"items[{idx}].sha256"
    )
    validated["size_bytes"] = _validate_non_negative(
        item.get("size_bytes", 0), f"items[{idx}].size_bytes"
    )
    validated["duration_ms"] = _validate_non_negative(
        item.get("duration_ms", 0), f"items[{idx}].duration_ms"
    )
    validated["order"] = _validate_non_negative(
        item.get("order", 0), f"items[{idx}].order"
    )
    return validated


def validate_local_manifest(data: Any) -> None:
    """Validate a local manifest dict. Raises ValueError on failure.

    Checks: top-level fields, items, forbidden keys/values.
    Never prints stacktrace or full manifest.
    """
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")

    # Security scan (recursive)
    _security_scan(data)

    # Top-level fields
    _validate_uuid(data.get("manifest_version_id"), "manifest_version_id")
    _validate_sha256(data.get("manifest_hash", ""), "manifest_hash")

    source = data.get("source", "")
    if source not in ("current", "by_id"):
        raise ValueError(f"source must be 'current' or 'by_id', got {source!r}")

    # Optional dates
    for field in ("generated_at", "valid_until", "fetched_at"):
        val = data.get(field)
        if val is not None and not isinstance(val, str):
            raise ValueError(f"{field}: must be a string or null")

    # Optional campaign_id
    cid = data.get("campaign_id")
    if cid is not None:
        _validate_uuid(cid, "campaign_id")

    # Items
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("'items' must be a list")

    for idx, item in enumerate(items):
        _validate_item(item, idx)


# ══════════════════════════════════════════════════════════════════════
# Normalize
# ══════════════════════════════════════════════════════════════════════

def normalize_manifest_snapshot(snapshot: Any, now: Optional[str] = None) -> dict:
    """Convert a ManifestSnapshot into the local manifest format.

    Args:
        snapshot: ManifestSnapshot from manifest_client.py.
        now: ISO8601 timestamp (defaults to current UTC).

    Returns:
        Normalized dict for local storage. Never contains secrets.
    """
    if now is None:
        now = _now_iso()

    # Extract snapshot fields
    status = getattr(snapshot, "status", "served")
    manifest_version_id = getattr(snapshot, "manifest_version_id", None)
    manifest_hash = getattr(snapshot, "manifest_hash", None)
    published_at = getattr(snapshot, "published_at", None)
    source = getattr(snapshot, "source", "unknown")
    items = getattr(snapshot, "items", [])

    # Normalize items
    normalized_items = []
    for item in (items or []):
        if not isinstance(item, dict):
            continue

        item_id = item.get("id") or item.get("manifest_item_id") or ""
        if not item_id:
            continue

        # Validate item_id is UUID
        try:
            _UUID(str(item_id))
        except (ValueError, AttributeError):
            continue

        # Content type from media_path extension
        media_path = item.get("media_path")
        content_type = _derive_content_type(media_path)

        # Filename from item_id + extension
        filename = _derive_filename(str(item_id), content_type)

        # sha256
        sha256 = item.get("sha256", "")
        if not isinstance(sha256, str) or not SHA256_RE.match(sha256):
            continue  # skip items with invalid sha256

        # Order: priority order > loop_position > spot_position > 0
        order = 0
        for key in ("order", "loop_position", "spot_position"):
            v = item.get(key)
            if isinstance(v, int) and v >= 0:
                order = v
                break

        duration_ms = item.get("duration_ms", 0)
        if not isinstance(duration_ms, int) or duration_ms < 0:
            duration_ms = 0

        normalized_items.append({
            "manifest_item_id": str(item_id),
            "filename": filename,
            "content_type": content_type,
            "sha256": sha256,
            "size_bytes": 0,
            "duration_ms": duration_ms,
            "order": order,
        })

    return {
        "manifest_version_id": manifest_version_id or "",
        "manifest_hash": manifest_hash or "",
        "source": source if source in ("current", "by_id") else "unknown",
        "generated_at": published_at or None,
        "valid_until": None,
        "fetched_at": now,
        "campaign_id": None,
        "items": normalized_items,
    }


# ══════════════════════════════════════════════════════════════════════
# Write / Read
# ══════════════════════════════════════════════════════════════════════

def write_current_manifest(
    root: str | Path,
    snapshot: Any,
    now: Optional[str] = None,
) -> dict:
    """Normalize and atomically write manifest/current_manifest.json.

    Args:
        root: Agent root path.
        snapshot: ManifestSnapshot from manifest_client.
        now: ISO8601 timestamp.

    Returns:
        Safe status dict: {status, manifest_version_id, items_count, ...}

    Never writes on not_modified or no_manifest.
    Never leaves .tmp files.
    Rejects symlink targets.
    """
    root = Path(root)
    status = getattr(snapshot, "status", "served")

    # ── not_modified: don't overwrite ──────────────────────────────
    if status == "not_modified":
        return {
            "status": "not_modified",
            "manifest_version_id": getattr(snapshot, "manifest_version_id", None),
            "items_count": 0,
            "message": "Manifest not modified, local file unchanged",
        }

    # ── no_manifest: don't create empty file ───────────────────────
    if status == "no_manifest":
        return {
            "status": "no_manifest",
            "manifest_version_id": None,
            "items_count": 0,
            "message": "No manifest available, local file unchanged",
        }

    # ── served: normalize → validate → write ──────────────────────
    if now is None:
        now = _now_iso()

    data = normalize_manifest_snapshot(snapshot, now=now)

    # Validate
    validate_local_manifest(data)

    # Atomic write
    target = root / CURRENT_MANIFEST_FILE
    atomic_write_json(target, data)

    return {
        "status": "written",
        "manifest_version_id": data["manifest_version_id"],
        "items_count": len(data["items"]),
        "fetched_at": now,
    }


def read_current_manifest(root: str | Path) -> dict:
    """Read and validate manifest/current_manifest.json.

    Returns validated dict. Raises FileNotFoundError if missing.
    Raises ValueError/JSONDecodeError on invalid content.
    """
    root = Path(root)
    path = root / CURRENT_MANIFEST_FILE

    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)

    validate_local_manifest(data)
    return data


def manifest_store_status(root: str | Path) -> dict:
    """Return safe summary of the local manifest store.

    Never prints full manifest or local_path.
    """
    root = Path(root)
    path = root / CURRENT_MANIFEST_FILE

    if not path.exists():
        return {
            "present": False,
            "manifest_version_id": None,
            "manifest_hash": None,
            "source": None,
            "generated_at": None,
            "fetched_at": None,
            "items_count": 0,
            "validation_status": "missing",
        }

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        validate_local_manifest(data)
    except Exception:
        return {
            "present": True,
            "manifest_version_id": None,
            "manifest_hash": None,
            "source": None,
            "generated_at": None,
            "fetched_at": None,
            "items_count": 0,
            "validation_status": "error",
        }

    mvid = data.get("manifest_version_id", "")
    mhash = data.get("manifest_hash", "")

    return {
        "present": True,
        "manifest_version_id": mvid[:12] + "..." if len(mvid) > 12 else mvid,
        "manifest_hash": mhash[:12] + "..." if len(mhash) > 12 else mhash,
        "source": data.get("source"),
        "generated_at": data.get("generated_at"),
        "fetched_at": data.get("fetched_at"),
        "items_count": len(data.get("items", [])),
        "validation_status": "ok",
    }
