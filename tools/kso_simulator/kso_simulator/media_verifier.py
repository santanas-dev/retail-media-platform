"""Verify local media files against manifest/current_manifest.json.

Follows kso_local_interface_contract.md.
This is a DEV TOOL. No secrets, no tokens, no network.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kso_simulator import manifest_reader


# ── Per-item verification status ────────────────────────────────────

ITEM_STATUS_OK = "ok"
ITEM_STATUS_MISSING = "missing"
ITEM_STATUS_HASH_MISMATCH = "hash_mismatch"
ITEM_STATUS_INVALID_ITEM = "invalid_manifest_item"
ITEM_STATUS_SYMLINK = "invalid_media_file"


# ── Result types ─────────────────────────────────────────────────────

@dataclass
class ItemResult:
    """Verification result for a single manifest item."""
    manifest_item_id: str
    filename: str
    expected_sha256: str
    status: str                      # one of ITEM_STATUS_*
    actual_sha256: str = ""          # set when file exists
    error: str = ""                  # human-readable error if not ok


@dataclass
class VerifyResult:
    """Aggregate media verification result."""
    total_items: int = 0
    present: int = 0
    missing: int = 0
    hash_ok: int = 0
    hash_mismatch: int = 0
    invalid_items: int = 0
    manifest_expired: bool = False
    items: list[ItemResult] = field(default_factory=list)


# ── SHA256 helper ────────────────────────────────────────────────────

def _compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hex digest of a file. Reads in chunks for large files."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ── Public API ───────────────────────────────────────────────────────

def verify_media(root: str | Path) -> VerifyResult:
    """Verify all media files listed in manifest exist and have correct hash.

    Returns a VerifyResult even when manifest is expired or items are invalid.
    Raises FileNotFoundError if manifest is missing.
    Raises ValueError if manifest JSON is invalid.
    """
    root = Path(root)
    media_dir = root / "media" / "current"
    manifest = manifest_reader.read_manifest(root)

    result = VerifyResult(
        total_items=manifest.items_count,
        manifest_expired=manifest.expired,
    )

    for item in manifest.items:
        if not _validate_item_fields(item):
            item_result = ItemResult(
                manifest_item_id=item.manifest_item_id,
                filename=item.filename,
                expected_sha256=item.sha256,
                status=ITEM_STATUS_INVALID_ITEM,
                error="Item missing required fields",
            )
            result.invalid_items += 1
            result.items.append(item_result)
            continue

        media_path = media_dir / item.filename

        # Reject symlinks before anything else
        if media_path.is_symlink():
            item_result = ItemResult(
                manifest_item_id=item.manifest_item_id,
                filename=item.filename,
                expected_sha256=item.sha256,
                status=ITEM_STATUS_SYMLINK,
                error="Symlinks not allowed",
            )
            result.invalid_items += 1
            result.items.append(item_result)
            continue

        # Resolve and check path stays inside media/current
        try:
            resolved = media_path.resolve()
        except (OSError, RuntimeError):
            item_result = ItemResult(
                manifest_item_id=item.manifest_item_id,
                filename=item.filename,
                expected_sha256=item.sha256,
                status=ITEM_STATUS_MISSING,
                error="Cannot resolve path",
            )
            result.missing += 1
            result.items.append(item_result)
            continue

        # Ensure the resolved path is inside the media/current directory
        try:
            resolved.relative_to(media_dir)
        except ValueError:
            item_result = ItemResult(
                manifest_item_id=item.manifest_item_id,
                filename=item.filename,
                expected_sha256=item.sha256,
                status=ITEM_STATUS_MISSING,
                error="Path escapes media/current",
            )
            result.missing += 1
            result.items.append(item_result)
            continue

        # Check if file exists
        if not resolved.exists():
            item_result = ItemResult(
                manifest_item_id=item.manifest_item_id,
                filename=item.filename,
                expected_sha256=item.sha256,
                status=ITEM_STATUS_MISSING,
                error="File not found",
            )
            result.missing += 1
            result.items.append(item_result)
            continue

        # File exists, compute hash
        try:
            actual = _compute_sha256(resolved)
        except OSError as e:
            item_result = ItemResult(
                manifest_item_id=item.manifest_item_id,
                filename=item.filename,
                expected_sha256=item.sha256,
                status=ITEM_STATUS_MISSING,
                error=f"Read error: {e}",
            )
            result.missing += 1
            result.items.append(item_result)
            continue

        result.present += 1

        if actual == item.sha256:
            item_result = ItemResult(
                manifest_item_id=item.manifest_item_id,
                filename=item.filename,
                expected_sha256=item.sha256,
                actual_sha256=actual,
                status=ITEM_STATUS_OK,
            )
            result.hash_ok += 1
        else:
            item_result = ItemResult(
                manifest_item_id=item.manifest_item_id,
                filename=item.filename,
                expected_sha256=item.sha256,
                actual_sha256=actual,
                status=ITEM_STATUS_HASH_MISMATCH,
                error="SHA256 does not match manifest",
            )
            result.hash_mismatch += 1

        result.items.append(item_result)

    return result


def _validate_item_fields(item) -> bool:
    """Quick check that item has all required non-trivial fields."""
    return bool(
        item.manifest_item_id
        and item.filename
        and item.sha256
        and item.content_type
    )
