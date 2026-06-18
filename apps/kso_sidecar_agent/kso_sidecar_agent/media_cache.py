"""Media Cache Local Store for KSO Sidecar Agent.

Atomic write of media files: staging → sha256 verify → current (or quarantine).
No backend calls, no secrets, no token/JWT/Authorization.
Compatible with tools/kso_simulator/kso_simulator/media_verifier.py.
"""

import hashlib as _hashlib
import os
import re as _re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from kso_sidecar_agent.paths import (
    MEDIA_CURRENT_DIR,
    MEDIA_QUARANTINE_DIR,
    MEDIA_STAGING_DIR,
)

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

PATH_TRAVERSAL_RE = _re.compile(r"\.\.|[\\/]|^[A-Za-z]:|^/")


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _compute_sha256(filepath: Path) -> str:
    """Compute sha256 of a file (streaming). Same as simulator/media_verifier.py."""
    sha = _hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _validate_filename(filename: str, field: str) -> str:
    """Validate filename is safe — no path traversal, no forbidden substrings."""
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError(f"{field}: must be a non-empty string")
    if PATH_TRAVERSAL_RE.search(filename):
        raise ValueError(f"{field}: path traversal not allowed in '{filename}'")
    lower = filename.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise ValueError(f"{field}: contains forbidden substring '{fb}'")
    return filename


def _check_forbidden(value: str, field: str) -> None:
    """Raise ValueError if value contains any forbidden substring."""
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise ValueError(f"Field '{field}' contains forbidden substring '{fb}'")


def _is_symlink(path: Path) -> bool:
    """Check if path or any parent is a symlink."""
    try:
        if path.is_symlink():
            return True
        # Check parents
        for parent in path.parents:
            if parent.is_symlink():
                return True
    except OSError:
        pass
    return False


def _resolve_safe(root: Path, filename: str) -> Path:
    """Resolve a safe path under root, rejecting symlinks and traversal."""
    target = (root / filename).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError:
        raise ValueError(f"Path traversal detected: '{filename}' escapes root")
    if _is_symlink(root / filename):
        raise ValueError(f"Symlink not allowed: '{filename}'")
    return root / filename  # return unresolved for atomic operations


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════
# Directory management
# ══════════════════════════════════════════════════════════════════════

def ensure_media_dirs(root: str | Path) -> dict:
    """Ensure media/{current,staging,quarantine} exist. Returns status dict."""
    root = Path(root)
    created = []
    for d in (MEDIA_CURRENT_DIR, MEDIA_STAGING_DIR, MEDIA_QUARANTINE_DIR):
        path = root / d
        if not path.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            created.append(d)
    return {
        "current_exists": (root / MEDIA_CURRENT_DIR).is_dir(),
        "staging_exists": (root / MEDIA_STAGING_DIR).is_dir(),
        "quarantine_exists": (root / MEDIA_QUARANTINE_DIR).is_dir(),
        "created": created,
    }


# ══════════════════════════════════════════════════════════════════════
# Write media atomic
# ══════════════════════════════════════════════════════════════════════

def write_media_atomic(
    root: str | Path,
    manifest_item: dict,
    media_content: Any,
    now: Optional[str] = None,
) -> dict:
    """Atomically write a media file: staging → sha256 verify → current (or quarantine).

    Args:
        root: Agent root path.
        manifest_item: Dict from local manifest/current_manifest.json items[].
                       Must have: filename, sha256, content_type, size_bytes.
        media_content: MediaContent object from media_client.py.
                       Must have: sha256, size_bytes, content_type, content (bytes).
        now: ISO8601 timestamp.

    Returns:
        Safe status dict with keys: status, filename, sha256_ok, size_ok, content_type_ok.
    """
    if now is None:
        now = _now_iso()

    root = Path(root)

    # Validate manifest_item
    if not isinstance(manifest_item, dict):
        raise ValueError("manifest_item must be a dict")

    filename = _validate_filename(manifest_item.get("filename", ""), "manifest_item.filename")
    expected_sha256 = manifest_item.get("sha256", "")
    if not isinstance(expected_sha256, str) or not SHA256_RE.match(expected_sha256):
        raise ValueError("manifest_item.sha256 must be 64 hex chars")
    expected_content_type = manifest_item.get("content_type", "")
    if not isinstance(expected_content_type, str) or not expected_content_type:
        raise ValueError("manifest_item.content_type is required")
    expected_size = manifest_item.get("size_bytes", 0)
    if not isinstance(expected_size, int) or expected_size < 0:
        raise ValueError(f"manifest_item.size_bytes must be >= 0, got {expected_size!r}")

    # Validate media_content
    content = getattr(media_content, "content", None)
    if content is None:
        content = getattr(media_content, "body_bytes", None)
    if not isinstance(content, bytes) or len(content) == 0:
        raise ValueError("media_content must have non-empty bytes")

    actual_sha256 = getattr(media_content, "sha256", "")
    if not isinstance(actual_sha256, str) or not SHA256_RE.match(actual_sha256):
        raise ValueError("media_content.sha256 must be 64 hex chars")

    actual_size = getattr(media_content, "size_bytes", 0)
    if not isinstance(actual_size, int):
        actual_size = len(content)

    actual_content_type = getattr(media_content, "content_type", "")

    # Verify sha256 match
    content_sha = _hashlib.sha256(content).hexdigest()
    if content_sha != expected_sha256:
        return {
            "status": "rejected",
            "filename": filename,
            "sha256_ok": False,
            "size_ok": True,
            "content_type_ok": True,
            "error": "SHA256 mismatch: content does not match manifest",
            "written_at": now,
        }

    # Verify size if expected > 0
    if expected_size > 0 and actual_size != expected_size:
        return {
            "status": "rejected",
            "filename": filename,
            "sha256_ok": True,
            "size_ok": False,
            "content_type_ok": True,
            "error": f"Size mismatch: expected {expected_size}, got {actual_size}",
            "written_at": now,
        }

    # Verify content_type
    if actual_content_type and actual_content_type != expected_content_type:
        return {
            "status": "rejected",
            "filename": filename,
            "sha256_ok": True,
            "size_ok": True,
            "content_type_ok": False,
            "error": f"Content-type mismatch: "
            f"expected {expected_content_type}, got {actual_content_type}",
            "written_at": now,
        }

    # Write to staging
    staging_dir = root / MEDIA_STAGING_DIR
    current_dir = root / MEDIA_CURRENT_DIR
    quarantine_dir = root / MEDIA_QUARANTINE_DIR

    staging_dir.mkdir(parents=True, exist_ok=True)

    staging_file = staging_dir / f"{filename}.download"

    # Reject symlinks
    if _is_symlink(staging_dir) or _is_symlink(current_dir):
        raise ValueError("Staging or current directory is a symlink — rejected")

    try:
        staging_file.write_bytes(content)
        with open(staging_file, "rb") as f:
            os.fsync(f.fileno())
    except Exception as e:
        # Clean up staging on failure
        if staging_file.exists():
            staging_file.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to write staging file: {e}") from e

    # Verify staging file sha256
    try:
        staging_sha = _compute_sha256(staging_file)
    except Exception as e:
        staging_file.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to verify staging file sha256: {e}") from e

    # Atomic move
    target_file = current_dir / filename
    try:
        if staging_sha == expected_sha256:
            current_dir.mkdir(parents=True, exist_ok=True)
            os.replace(staging_file, target_file)
            return {
                "status": "written",
                "filename": filename,
                "sha256_ok": True,
                "size_ok": True,
                "content_type_ok": True,
                "written_at": now,
            }
        else:
            # sha256 mismatch on disk
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            os.replace(staging_file, quarantine_dir / f"{filename}.bad")
            return _move_to_quarantine(root, filename, reason="sha256 mismatch on disk")
    except Exception:
        # Clean up staging on failure
        if staging_file.exists():
            staging_file.unlink(missing_ok=True)
        raise


def _move_to_quarantine(root: Path, filename: str, reason: str) -> dict:
    """Move a file to quarantine. Returns status dict."""
    # Check reason for forbidden substrings
    _check_forbidden(reason, "quarantine_reason")

    current_file = root / MEDIA_CURRENT_DIR / filename
    quarantine_dir = root / MEDIA_QUARANTINE_DIR
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = quarantine_dir / f"{filename}.bad"

    if current_file.exists():
        os.replace(current_file, target)

    return {
        "status": "quarantined",
        "filename": filename,
        "sha256_ok": False,
        "size_ok": True,
        "content_type_ok": True,
        "error": reason,
        "written_at": _now_iso(),
    }


# ══════════════════════════════════════════════════════════════════════
# Verify existing media
# ══════════════════════════════════════════════════════════════════════

def verify_media_file(root: str | Path, manifest_item: dict) -> dict:
    """Verify a media file in media/current/ against its manifest item.

    Args:
        root: Agent root path.
        manifest_item: Dict from local manifest items[]. Must have filename, sha256, size_bytes.

    Returns:
        {status, filename, sha256_ok, size_ok, exists, error, verified_at}
    """
    root = Path(root)

    filename = _validate_filename(manifest_item.get("filename", ""), "manifest_item.filename")
    expected_sha256 = manifest_item.get("sha256", "")
    if not isinstance(expected_sha256, str) or not SHA256_RE.match(expected_sha256):
        raise ValueError("manifest_item.sha256 must be 64 hex chars")
    expected_size = manifest_item.get("size_bytes", 0)

    filepath = root / MEDIA_CURRENT_DIR / filename

    if not filepath.exists():
        return {
            "status": "missing",
            "filename": filename,
            "sha256_ok": False,
            "size_ok": False,
            "exists": False,
            "error": "File not found in media/current",
            "verified_at": _now_iso(),
        }

    if filepath.is_symlink():
        return {
            "status": "rejected",
            "filename": filename,
            "sha256_ok": False,
            "size_ok": False,
            "exists": True,
            "error": "Symlink not allowed",
            "verified_at": _now_iso(),
        }

    actual_size = filepath.stat().st_size
    size_ok = True
    if expected_size > 0 and actual_size != expected_size:
        size_ok = False

    try:
        actual_sha = _compute_sha256(filepath)
    except Exception as e:
        return {
            "status": "error",
            "filename": filename,
            "sha256_ok": False,
            "size_ok": size_ok,
            "exists": True,
            "error": f"Failed to read file: {e}",
            "verified_at": _now_iso(),
        }

    sha_ok = actual_sha == expected_sha256

    if sha_ok and size_ok:
        return {
            "status": "ok",
            "filename": filename,
            "sha256_ok": True,
            "size_ok": True,
            "exists": True,
            "verified_at": _now_iso(),
        }

    return {
        "status": "invalid",
        "filename": filename,
        "sha256_ok": sha_ok,
        "size_ok": size_ok,
        "exists": True,
        "error": f"{'sha256' if not sha_ok else ''}{' and ' if not sha_ok and not size_ok else ''}{'size' if not size_ok else ''} mismatch",
        "verified_at": _now_iso(),
    }


# ══════════════════════════════════════════════════════════════════════
# Media cache status
# ══════════════════════════════════════════════════════════════════════

def media_cache_status(
    root: str | Path,
    manifest_items: Optional[list] = None,
) -> dict:
    """Return safe summary of the local media cache.

    If manifest_items provided: checks each item against media/current/.
    If not provided: returns counts only (no manifest dependency).

    Args:
        root: Agent root path.
        manifest_items: Optional list of manifest item dicts from current_manifest.json.

    Returns:
        Safe status dict. Never prints full local_path or manifest.
    """
    root = Path(root)

    current_dir = root / MEDIA_CURRENT_DIR
    staging_dir = root / MEDIA_STAGING_DIR
    quarantine_dir = root / MEDIA_QUARANTINE_DIR

    if manifest_items is not None:
        items_total = len(manifest_items)
        items_cached = 0
        items_missing = 0
        items_invalid_hash = 0
        items_invalid_size = 0

        for item in manifest_items:
            filename = item.get("filename", "")
            if not filename:
                items_missing += 1
                continue

            filepath = current_dir / filename
            if not filepath.exists():
                items_missing += 1
                continue

            try:
                actual_sha = _compute_sha256(filepath)
                expected_sha = item.get("sha256", "")
                if actual_sha == expected_sha:
                    items_cached += 1
                else:
                    items_invalid_hash += 1
            except Exception:
                items_invalid_hash += 1
                continue

            expected_size = item.get("size_bytes", 0)
            if expected_size > 0:
                actual_size = filepath.stat().st_size
                if actual_size != expected_size:
                    items_invalid_size += 1

        return {
            "present": True,
            "items_total": items_total,
            "items_cached": items_cached,
            "items_missing": items_missing,
            "items_invalid_hash": items_invalid_hash,
            "items_invalid_size": items_invalid_size,
            "cache_complete": (items_cached == items_total),
        }

    # No manifest — just counts
    current_files = list(current_dir.iterdir()) if current_dir.is_dir() else []
    staging_files = list(staging_dir.iterdir()) if staging_dir.is_dir() else []
    quarantine_files = list(quarantine_dir.iterdir()) if quarantine_dir.is_dir() else []

    return {
        "present": current_dir.is_dir(),
        "current_files_count": len(current_files),
        "staging_files_count": len(staging_files),
        "quarantine_files_count": len(quarantine_files),
    }


# ══════════════════════════════════════════════════════════════════════
# Quarantine a file
# ══════════════════════════════════════════════════════════════════════

def quarantine_media_file(
    root: str | Path,
    filename: str,
    reason: Optional[str] = None,
) -> dict:
    """Move a media file from current to quarantine.

    Args:
        root: Agent root path.
        filename: Safe filename (no path).
        reason: Safe reason string (no forbidden substrings).

    Returns:
        Status dict: {status, filename, moved}
    """
    root = Path(root)

    filename = _validate_filename(filename, "filename")
    if reason:
        _check_forbidden(reason, "reason")

    current_file = root / MEDIA_CURRENT_DIR / filename
    quarantine_dir = root / MEDIA_QUARANTINE_DIR

    if _is_symlink(current_file):
        raise ValueError(f"Symlink not allowed: '{filename}'")

    if not current_file.exists():
        return {
            "status": "not_found",
            "filename": filename,
            "moved": False,
            "error": "File not found in media/current",
        }

    quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = quarantine_dir / f"{filename}.bad"

    os.replace(current_file, target)

    return {
        "status": "quarantined",
        "filename": filename,
        "moved": True,
        "reason": reason,
        "quarantined_at": _now_iso(),
    }
