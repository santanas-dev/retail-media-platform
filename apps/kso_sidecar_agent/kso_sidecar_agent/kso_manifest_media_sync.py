"""KSO Sidecar — Manifest + Media Sync Core.

Orchestrates the full KSO sync cycle:
  1. Fetch gateway manifest response (via injectable gateway client)
  2. Extract safe manifest body
  3. Download media by items[].mediaRef
  4. Atomically write media files (media first)
  5. Atomically write manifest (manifest last)

Rule: NEVER publish manifest before its media is ready.
If any media download fails → old manifest preserved, no partial state.

No backend calls in tests — gateway_client is injectable.
No PoP, no systemd, no state writes, no secrets.
"""

import os
import re as _re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol

from kso_sidecar_agent.atomic_io import atomic_write_json
from kso_sidecar_agent.paths import CURRENT_MANIFEST_FILE, MEDIA_CURRENT_DIR
from kso_sidecar_agent.kso_manifest_gateway_extractor import (
    extract_kso_safe_manifest_body_from_gateway_response,
    KsoGatewayManifestExtractionResult,
    STATUS_OK as EXTRACT_OK,
    STATUS_NOT_MODIFIED as EXTRACT_NOT_MODIFIED,
    STATUS_NO_MANIFEST as EXTRACT_NO_MANIFEST,
    STATUS_ERROR as EXTRACT_ERROR,
    REASON_SERVED,
    REASON_NOT_MODIFIED as EXTRACT_REASON_NOT_MODIFIED,
    REASON_NO_MANIFEST as EXTRACT_REASON_NO_MANIFEST,
    ALLOWED_CONTENT_TYPES as KSO_ALLOWED_CONTENT_TYPES,
)

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

MAX_MEDIA_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB per file

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_NOT_MODIFIED = "not_modified"
STATUS_NO_MANIFEST = "no_manifest"

REASON_SYNCED = "synced"
REASON_NOT_MODIFIED = "not_modified"
REASON_NO_MANIFEST = "no_manifest"
REASON_MEDIA_DOWNLOAD_FAILED = "media_download_failed"
REASON_CONTENT_TYPE_MISMATCH = "content_type_mismatch"
REASON_MEDIA_TOO_LARGE = "media_too_large"
REASON_MEDIA_WRITE_FAILED = "media_write_failed"
REASON_MANIFEST_WRITE_FAILED = "manifest_write_failed"
REASON_MANIFEST_EXTRACTION_FAILED = "manifest_extraction_failed"
REASON_INVALID_ARGS = "invalid_args"

# ══════════════════════════════════════════════════════════════════════
# Gateway client contract (injectable)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoMediaDownloadResponse:
    """Response from gateway_client.download_kso_media().

    Only safe fields — NO internal IDs, paths, storage keys.
    """

    status: str = STATUS_ERROR
    content_type: str = ""
    content_length: int = 0
    body: bytes = field(default=b"", repr=False)

    def __repr__(self) -> str:
        return (
            f"KsoMediaDownloadResponse("
            f"status={self.status!r}, "
            f"content_type={self.content_type!r}, "
            f"content_length={self.content_length})"
        )


class KsoGatewayClient(Protocol):
    """Injectable gateway client contract.

    Tests use fake implementations — no real HTTP.
    """

    def fetch_current_manifest(self) -> Mapping[str, Any]:
        """Return raw gateway response dict."""
        ...

    def download_kso_media(self, media_ref: str) -> KsoMediaDownloadResponse:
        """Download a media file by safe mediaRef."""
        ...


# ══════════════════════════════════════════════════════════════════════
# Result types
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KsoManifestMediaSyncResult:
    """Safe result of KSO manifest + media sync.

    NEVER contains: paths, filenames, mediaRef values, IDs,
    raw JSON, raw response, manifest_version_id, manifest_hash,
    exception text, stacktrace.
    """

    status: str = STATUS_ERROR
    manifest_written: bool = False
    media_downloaded_count: int = 0
    media_written_count: int = 0
    items_count: int = 0
    reason: str = REASON_INVALID_ARGS

    # Internal — NEVER exposed in repr/format
    _errors: List[str] = field(default_factory=list, repr=False)

    def __repr__(self) -> str:
        return (
            f"KsoManifestMediaSyncResult("
            f"status={self.status!r}, "
            f"manifest_written={self.manifest_written}, "
            f"media_downloaded_count={self.media_downloaded_count}, "
            f"media_written_count={self.media_written_count}, "
            f"items_count={self.items_count}, "
            f"reason={self.reason!r})"
        )


# ══════════════════════════════════════════════════════════════════════
# Helpers — atomic media write
# ══════════════════════════════════════════════════════════════════════

def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write bytes atomically: write to .tmp, fsync, rename.

    Raises OSError on failure.
    """
    target = target.resolve()
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(parent),
        prefix="." + target.name + ".",
        suffix=".tmp",
    )
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)

    try:
        os.replace(tmp_path, str(target))
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ══════════════════════════════════════════════════════════════════════
# Helpers — validation
# ══════════════════════════════════════════════════════════════════════

_SLOT_PATTERN = _re.compile(r"^media/current/slot-(\d{3})$")


def _validate_media_ref_slot(media_ref: str) -> Optional[int]:
    """Validate mediaRef as media/current/slot-NNN. Returns slot index or None."""
    if not isinstance(media_ref, str) or not media_ref.strip():
        return None
    if ".." in media_ref or "\\" in media_ref:
        return None
    if media_ref.startswith("/"):
        return None
    lower = media_ref.lower()
    for unsafe in ("://", "http:", "https:", "file:", "%2e", "%2f"):
        if unsafe in lower:
            return None
    m = _SLOT_PATTERN.match(media_ref)
    if not m:
        return None
    slot = int(m.group(1))
    return slot if 0 <= slot <= 999 else None


# ══════════════════════════════════════════════════════════════════════
# Core API
# ══════════════════════════════════════════════════════════════════════

def sync_kso_manifest_and_media(
    root,
    gateway_client: KsoGatewayClient,
    now: Optional[datetime] = None,
) -> KsoManifestMediaSyncResult:
    """Sync KSO manifest + media from gateway.

    Full cycle:
      1. fetch_current_manifest()
      2. Extract safe manifest body
      3. If not_modified / no_manifest → no-op
      4. If items empty → write manifest
      5. Download each mediaRef → validate → atomic write
      6. After ALL media done → atomic write manifest

    Args:
        root: Agent root path (str or Path).
        gateway_client: Injectable client implementing KsoGatewayClient.
        now: Optional datetime for test time injection.

    Returns:
        KsoManifestMediaSyncResult — safe aggregate, never raises.
    """
    errors: List[str] = []

    # ── Validate args ──────────────────────────────────────────────
    try:
        root = Path(root)
    except (TypeError, ValueError):
        return KsoManifestMediaSyncResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    if gateway_client is None:
        return KsoManifestMediaSyncResult(
            status=STATUS_ERROR,
            reason=REASON_INVALID_ARGS,
        )

    if now is None:
        now = datetime.now(timezone.utc)

    # ── Step 1: Fetch manifest ────────────────────────────────────
    try:
        response = gateway_client.fetch_current_manifest()
    except Exception:
        return KsoManifestMediaSyncResult(
            status=STATUS_ERROR,
            reason=REASON_MANIFEST_EXTRACTION_FAILED,
            _errors=["Gateway fetch failed"],
        )

    # ── Step 2: Extract safe manifest body ─────────────────────────
    try:
        extraction = extract_kso_safe_manifest_body_from_gateway_response(
            response)
    except Exception:
        return KsoManifestMediaSyncResult(
            status=STATUS_ERROR,
            reason=REASON_MANIFEST_EXTRACTION_FAILED,
            _errors=["Extraction raised exception"],
        )

    # ── Handle non-served statuses ─────────────────────────────────
    if extraction.status == EXTRACT_NOT_MODIFIED:
        return KsoManifestMediaSyncResult(
            status=STATUS_NOT_MODIFIED,
            reason=REASON_NOT_MODIFIED,
        )

    if extraction.status == EXTRACT_NO_MANIFEST:
        return KsoManifestMediaSyncResult(
            status=STATUS_NO_MANIFEST,
            reason=REASON_NO_MANIFEST,
        )

    if not extraction.extracted:
        return KsoManifestMediaSyncResult(
            status=STATUS_ERROR,
            reason=extraction.reason,
            _errors=extraction._errors,
        )

    # ── Get manifest body ──────────────────────────────────────────
    manifest_body = extraction._manifest_body
    items = manifest_body.get("items", [])
    if not isinstance(items, list):
        items = []

    items_count = len(items)

    # ── Empty items: write manifest, skip media ────────────────────
    if items_count == 0:
        target = root / CURRENT_MANIFEST_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            atomic_write_json(target, manifest_body)
            return KsoManifestMediaSyncResult(
                status=STATUS_OK,
                manifest_written=True,
                media_downloaded_count=0,
                media_written_count=0,
                items_count=0,
                reason=REASON_SYNCED,
            )
        except Exception:
            return KsoManifestMediaSyncResult(
                status=STATUS_ERROR,
                reason=REASON_MANIFEST_WRITE_FAILED,
            )

    # ── Step 3: Download and validate each media ───────────────────
    downloaded: List[tuple[str, bytes, str]] = []  # (media_ref, body, content_type)

    for item in items:
        if not isinstance(item, dict):
            continue

        media_ref = item.get("mediaRef", "")
        expected_ct = item.get("contentType", "")

        if not isinstance(media_ref, str) or _validate_media_ref_slot(media_ref) is None:
            errors.append(f"Invalid mediaRef in manifest item")
            continue

        if not isinstance(expected_ct, str) or not expected_ct.strip():
            errors.append(f"Missing contentType in manifest item")
            continue

        expected_ct = expected_ct.strip().lower()

        if expected_ct not in KSO_ALLOWED_CONTENT_TYPES:
            errors.append(f"Unsupported contentType: {expected_ct}")
            continue

        # Download
        try:
            dl = gateway_client.download_kso_media(media_ref)
        except Exception:
            errors.append("Media download failed")
            continue

        if dl.status != STATUS_OK:
            errors.append("Media download failed")
            continue

        if not dl.body:
            errors.append("Media download returned empty body")
            continue

        # Validate content type matches
        dl_ct = dl.content_type.strip().lower() if dl.content_type else ""
        if dl_ct and dl_ct != expected_ct:
            return KsoManifestMediaSyncResult(
                status=STATUS_ERROR,
                reason=REASON_CONTENT_TYPE_MISMATCH,
                items_count=items_count,
                _errors=[f"Expected {expected_ct}, got {dl_ct}"],
            )

        # Validate size
        if dl.content_length > MAX_MEDIA_SIZE_BYTES:
            return KsoManifestMediaSyncResult(
                status=STATUS_ERROR,
                reason=REASON_MEDIA_TOO_LARGE,
                items_count=items_count,
                _errors=[f"Media too large: {dl.content_length} > {MAX_MEDIA_SIZE_BYTES}"],
            )

        downloaded.append((media_ref, dl.body, dl_ct or expected_ct))

    media_downloaded_count = len(downloaded)

    if errors and media_downloaded_count == 0:
        return KsoManifestMediaSyncResult(
            status=STATUS_ERROR,
            reason=REASON_MEDIA_DOWNLOAD_FAILED,
            items_count=items_count,
            media_downloaded_count=0,
            _errors=errors,
        )

    # ── Step 4: Write media files atomically ────────────────────────
    media_written_count = 0
    for media_ref, body, ct in downloaded:
        # Extract slot-NNN from mediaRef
        filename = Path(media_ref).name  # "slot-000"
        target = root / MEDIA_CURRENT_DIR / filename

        try:
            _atomic_write_bytes(target, body)
            media_written_count += 1
        except OSError:
            # Media write failed → don't publish manifest
            return KsoManifestMediaSyncResult(
                status=STATUS_ERROR,
                reason=REASON_MEDIA_WRITE_FAILED,
                media_downloaded_count=media_downloaded_count,
                media_written_count=media_written_count,
                items_count=items_count,
                _errors=[f"Failed to write media file"],
            )

    # ── Step 5: Write manifest (media is ready) ─────────────────────
    manifest_target = root / CURRENT_MANIFEST_FILE
    manifest_target.parent.mkdir(parents=True, exist_ok=True)

    try:
        atomic_write_json(manifest_target, manifest_body)
    except Exception:
        return KsoManifestMediaSyncResult(
            status=STATUS_ERROR,
            reason=REASON_MANIFEST_WRITE_FAILED,
            media_downloaded_count=media_downloaded_count,
            media_written_count=media_written_count,
            items_count=items_count,
        )

    return KsoManifestMediaSyncResult(
        status=STATUS_OK,
        manifest_written=True,
        media_downloaded_count=media_downloaded_count,
        media_written_count=media_written_count,
        items_count=items_count,
        reason=REASON_SYNCED,
    )


# ══════════════════════════════════════════════════════════════════════
# Formatter
# ══════════════════════════════════════════════════════════════════════

def format_kso_manifest_media_sync_result(
    result: KsoManifestMediaSyncResult,
) -> str:
    """Format sync result as safe human-readable string.

    NEVER contains: paths, filenames, mediaRef values, IDs,
    raw JSON, exception text, stacktrace.
    """
    lines = [
        f"status: {result.status}",
        f"manifest_written: {str(result.manifest_written).lower()}",
        f"media_downloaded_count: {result.media_downloaded_count}",
        f"media_written_count: {result.media_written_count}",
        f"items_count: {result.items_count}",
        f"reason: {result.reason}",
    ]
    return "\n".join(lines)
