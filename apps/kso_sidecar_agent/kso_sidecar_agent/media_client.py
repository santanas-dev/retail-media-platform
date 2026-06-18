"""Media Client for KSO Sidecar Agent.

Fetches media metadata and content from backend via:
  GET /api/device-gateway/media/{manifest_item_id}/metadata
  GET /api/device-gateway/media/{manifest_item_id}

All data stays in memory only — no disk writes.
Never logs Authorization header, response body, or secrets.
"""

import hashlib as _hashlib
import re as _re
import time as _time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID as _UUID

from kso_sidecar_agent.http_client import (
    HttpClientError,
    HttpBinaryResponse,
    HttpResponse,
    SafeHttpClient,
)
from kso_sidecar_agent.token_state import TokenState

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

# Allowed MIME types — matches backend MEDIA_DELIVERY_ALLOWED_MIME
ALLOWED_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "video/mp4",
    "video/webm",
})

SHA256_RE = _re.compile(r"^[0-9a-fA-F]{64}$")

FORBIDDEN_MEDIA_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
})

# Backend endpoints
METADATA_PATH = "/api/device-gateway/media/{manifest_item_id}/metadata"
MEDIA_PATH = "/api/device-gateway/media/{manifest_item_id}"


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _validate_uuid(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}: must be a string, got {type(value).__name__}")
    try:
        _UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"{field}: '{value}' is not a valid UUID")
    return value


def _validate_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}: sha256 must be a string")
    if not SHA256_RE.match(value):
        raise ValueError(f"{field}: must be 64 hex chars, got {len(value)}")
    return value


def _validate_mime(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field}: must be a non-empty string")
    if value not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"{field}: '{value}' not in allowed MIME types"
        )
    return value


def _check_forbidden(value: str, field_path: str) -> None:
    """Raise ValueError if value contains any forbidden substring."""
    lower = value.lower()
    for forbidden in FORBIDDEN_MEDIA_SUBSTRINGS:
        if forbidden in lower:
            raise ValueError(
                f"Media field '{field_path}' contains forbidden substring '{forbidden}'"
            )


def _compute_sha256(data: bytes) -> str:
    return _hashlib.sha256(data).hexdigest()


# ══════════════════════════════════════════════════════════════════════
# MediaMetadata
# ══════════════════════════════════════════════════════════════════════

@dataclass
class MediaMetadata:
    """Metadata for a single manifest item — memory only, no disk.

    Fields match backend GET /media/{id}/metadata response.
    """

    manifest_item_id: str
    sha256: str
    content_type: str
    size_bytes: int = 0
    duration_ms: Optional[int] = None
    status: str = "ok"
    fetched_at: Optional[float] = None

    def safe_summary(self) -> dict:
        """Return metadata only — no secrets, no full sha256."""
        return {
            "manifest_item_id": self.manifest_item_id[:12] + "...",
            "sha256": self.sha256[:12] + "...",
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "fetched_at": self.fetched_at,
        }


# ══════════════════════════════════════════════════════════════════════
# MediaContent
# ══════════════════════════════════════════════════════════════════════

@dataclass
class MediaContent:
    """Downloaded media content — memory only, no disk.

    Never exposes raw bytes in safe_summary().
    """

    manifest_item_id: str
    sha256: str
    size_bytes: int
    content_type: str
    content: bytes = field(repr=False)
    fetched_at: Optional[float] = None

    def safe_summary(self) -> dict:
        """Return metadata only — no content bytes, no secrets."""
        return {
            "manifest_item_id": self.manifest_item_id[:12] + "...",
            "sha256": self.sha256[:12] + "...",
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "fetched_at": self.fetched_at,
        }


# ══════════════════════════════════════════════════════════════════════
# MediaClient
# ══════════════════════════════════════════════════════════════════════

class MediaClient:
    """Fetches media metadata and content from backend. Token stays in memory only.

    Does NOT write media to disk (that will be a separate step).
    Does NOT implement retry (that will be a separate step).
    Never logs Authorization header or response body.
    """

    METADATA_PATH = METADATA_PATH
    MEDIA_PATH = MEDIA_PATH

    def __init__(
        self,
        http_client: SafeHttpClient,
        logger: Optional[Any] = None,
    ) -> None:
        self._http = http_client
        self._log = logger

    # ── fetch_metadata ───────────────────────────────────────────────

    def fetch_metadata(
        self,
        token_state: TokenState,
        manifest_item_id: str,
        now: Optional[float] = None,
    ) -> MediaMetadata:
        """Fetch media metadata from backend.

        Args:
            token_state: Valid TokenState with access_token.
            manifest_item_id: UUID of the manifest item.
            now: Current timestamp (defaults to time.time()).

        Returns:
            MediaMetadata with sha256, content_type, size_bytes, duration_ms.

        Raises:
            ValueError: Token invalid, manifest_item_id invalid, validation failed.
            HttpClientError: HTTP-level failure.
        """
        if now is None:
            now = _time.time()

        # Validate token (NOT retryable — no HTTP request)
        if not token_state.is_valid(now=now):
            raise ValueError("Token is missing or expired — cannot fetch media metadata")

        # Validate manifest_item_id (NOT retryable — no HTTP request)
        _validate_uuid(manifest_item_id, "manifest_item_id")

        auth_header = token_state.authorization_header(now=now)
        headers = {"Authorization": auth_header}

        path = self.METADATA_PATH.format(manifest_item_id=manifest_item_id)

        try:
            resp: HttpResponse = self._http.get_json(path, headers=headers)
        except HttpClientError as e:
            if self._log:
                self._log.log(
                    level="error",
                    event="media_metadata_failed",
                    message=f"Media metadata fetch failed: {e}",
                )
            raise

        return self._parse_metadata_response(resp, manifest_item_id, now)

    def _parse_metadata_response(
        self, resp: HttpResponse, manifest_item_id: str, now: float,
    ) -> MediaMetadata:
        """Parse and validate the /media/{id}/metadata response."""
        body = resp.json_body

        if not isinstance(body, dict):
            raise HttpClientError(
                status_code=resp.status_code,
                message="Invalid metadata response: expected JSON object",
                retryable=False,
            )

        st = body.get("status", "unknown")

        # not_modified
        if st in ("not_modified", "304"):
            # Return metadata stub with not_modified status
            sha = body.get("sha256", "")
            if sha:
                _validate_sha256(sha, "metadata.sha256")
            return MediaMetadata(
                manifest_item_id=manifest_item_id,
                sha256=sha,
                content_type="",
                size_bytes=0,
                status="not_modified",
                fetched_at=now,
            )

        if st not in ("ok", "served"):
            raise HttpClientError(
                status_code=resp.status_code,
                message=f"Unexpected metadata status: {st}",
                retryable=False,
            )

        # Extract media field
        media = body.get("media")
        if not isinstance(media, dict):
            raise HttpClientError(
                status_code=resp.status_code,
                message="Invalid metadata: missing 'media' object",
                retryable=False,
            )

        try:
            # Validate sha256
            sha256 = media.get("sha256", "")
            _validate_sha256(sha256, "media.sha256")

            # Validate content_type
            content_type = media.get("content_type", "")
            _validate_mime(content_type, "media.content_type")

            # Validate size_bytes
            size_bytes = media.get("size_bytes", 0)
            if not isinstance(size_bytes, int) or size_bytes < 0:
                raise ValueError(
                    f"media.size_bytes must be >= 0, got {size_bytes!r}"
                )
        except ValueError as e:
            raise HttpClientError(
                status_code=resp.status_code,
                message=str(e),
                retryable=False,
            ) from None

        # Validate duration_ms (optional)
        duration_ms = media.get("duration_ms")
        if duration_ms is not None:
            if not isinstance(duration_ms, int) or duration_ms < 0:
                raise ValueError(
                    f"media.duration_ms must be >= 0, got {duration_ms!r}"
                )

        # Forbidden scan on all string values
        for key, value in media.items():
            if isinstance(value, str):
                _check_forbidden(value, f"media.{key}")

        result = MediaMetadata(
            manifest_item_id=manifest_item_id,
            sha256=sha256,
            content_type=content_type,
            size_bytes=size_bytes,
            duration_ms=duration_ms,
            status="ok",
            fetched_at=now,
        )

        if self._log:
            self._log.log(
                level="info",
                event="media_metadata_fetched",
                message="Media metadata fetched successfully",
                extra=result.safe_summary(),
            )

        return result

    # ── fetch_media ──────────────────────────────────────────────────

    def fetch_media(
        self,
        token_state: TokenState,
        manifest_item_id: str,
        expected_sha256: Optional[str] = None,
        expected_size_bytes: Optional[int] = None,
        expected_content_type: Optional[str] = None,
        max_bytes: Optional[int] = None,
        now: Optional[float] = None,
    ) -> MediaContent:
        """Fetch media content (binary) from backend.

        Args:
            token_state: Valid TokenState with access_token.
            manifest_item_id: UUID of the manifest item.
            expected_sha256: If provided, validate downloaded content against this.
            expected_size_bytes: If provided and > 0, validate Content-Length / actual size.
            expected_content_type: If provided, validate Content-Type header.
            max_bytes: Max allowed response size. Raises error if exceeded.
            now: Current timestamp (defaults to time.time()).

        Returns:
            MediaContent with content bytes, sha256, size, content_type.

        Raises:
            ValueError: Token invalid, manifest_item_id invalid, validation failed.
            HttpClientError: HTTP/network/size-limit errors.
        """
        if now is None:
            now = _time.time()

        # Validate token (NOT retryable — no HTTP request)
        if not token_state.is_valid(now=now):
            raise ValueError("Token is missing or expired — cannot fetch media")

        # Validate manifest_item_id (NOT retryable — no HTTP request)
        _validate_uuid(manifest_item_id, "manifest_item_id")

        auth_header = token_state.authorization_header(now=now)
        headers = {"Authorization": auth_header}

        path = self.MEDIA_PATH.format(manifest_item_id=manifest_item_id)

        try:
            resp: HttpBinaryResponse = self._http.get_bytes(
                path, headers=headers, max_bytes=max_bytes,
            )
        except HttpClientError as e:
            if self._log:
                self._log.log(
                    level="error",
                    event="media_download_failed",
                    message=f"Media download failed: {e}",
                )
            raise

        return self._parse_media_response(
            resp, manifest_item_id, now,
            expected_sha256=expected_sha256,
            expected_size_bytes=expected_size_bytes,
            expected_content_type=expected_content_type,
        )

    def _parse_media_response(
        self,
        resp: HttpBinaryResponse,
        manifest_item_id: str,
        now: float,
        expected_sha256: Optional[str] = None,
        expected_size_bytes: Optional[int] = None,
        expected_content_type: Optional[str] = None,
    ) -> MediaContent:
        """Parse and validate binary media response."""
        content = resp.body_bytes
        actual_size = len(content)

        # Check headers
        content_type_header = resp.headers.get("Content-Type", "")

        # X-Content-SHA256 header
        header_sha256 = resp.headers.get("X-Content-SHA256", "")
        if header_sha256:
            _validate_sha256(header_sha256, "X-Content-SHA256 header")
            # Verify header sha256 matches actual content
            actual_sha256 = _compute_sha256(content)
            if header_sha256.lower() != actual_sha256.lower():
                raise HttpClientError(
                    status_code=resp.status_code,
                    message="Media sha256 mismatch: X-Content-SHA256 header vs actual content",
                    retryable=False,
                )

        # Content-Length header
        content_length_header = resp.headers.get("Content-Length", "")
        if content_length_header:
            try:
                cl = int(content_length_header)
                if cl != actual_size:
                    raise HttpClientError(
                        status_code=resp.status_code,
                        message=f"Media size mismatch: "
                        f"Content-Length={cl} vs actual={actual_size}",
                        retryable=False,
                    )
            except ValueError:
                pass  # non-integer Content-Length — ignore

        # Compute actual sha256 of content
        actual_sha256 = _compute_sha256(content)

        # Validate expected_sha256
        if expected_sha256:
            _validate_sha256(expected_sha256, "expected_sha256")
            if actual_sha256.lower() != expected_sha256.lower():
                raise HttpClientError(
                    status_code=resp.status_code,
                    message="Media sha256 mismatch: expected vs actual",
                    retryable=False,
                )

        # Validate expected_size_bytes
        if expected_size_bytes is not None and expected_size_bytes > 0:
            if not isinstance(expected_size_bytes, int) or expected_size_bytes < 0:
                raise ValueError(
                    f"expected_size_bytes must be >= 0, got {expected_size_bytes!r}"
                )
            if actual_size != expected_size_bytes:
                raise HttpClientError(
                    status_code=resp.status_code,
                    message=f"Media size mismatch: expected {expected_size_bytes} vs actual {actual_size}",
                    retryable=False,
                )

        # Validate expected_content_type
        resolved_ct = content_type_header
        if expected_content_type:
            _validate_mime(expected_content_type, "expected_content_type")
            if resolved_ct and resolved_ct != expected_content_type:
                raise HttpClientError(
                    status_code=resp.status_code,
                    message=f"Media content_type mismatch: "
                    f"expected {expected_content_type} vs actual {resolved_ct}",
                    retryable=False,
                )
            resolved_ct = expected_content_type
        elif not resolved_ct:
            # No Content-Type header and no expected — can't determine type
            raise HttpClientError(
                status_code=resp.status_code,
                message="Media response missing Content-Type header",
                retryable=False,
            )
        else:
            # Validate Content-Type from header
            try:
                _validate_mime(resolved_ct, "Content-Type header")
            except ValueError as e:
                raise HttpClientError(
                    status_code=resp.status_code,
                    message=str(e),
                    retryable=False,
                ) from None

        result = MediaContent(
            manifest_item_id=manifest_item_id,
            sha256=actual_sha256,
            size_bytes=actual_size,
            content_type=resolved_ct,
            content=content,
            fetched_at=now,
        )

        if self._log:
            self._log.log(
                level="info",
                event="media_downloaded",
                message="Media downloaded successfully",
                extra=result.safe_summary(),
            )

        return result
