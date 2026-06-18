"""Media Cache Report Client for KSO Sidecar Agent.

Builds and sends POST /api/device-gateway/media/cache/report.
Uses local manifest + media_cache_status + verify_media_file.
Never logs Authorization header, request/response body, or secrets.
"""

import re as _re
import time as _time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID as _UUID

from kso_sidecar_agent.http_client import HttpClientError, HttpResponse, SafeHttpClient
from kso_sidecar_agent import manifest_store as _manifest_store
from kso_sidecar_agent import media_cache as _media_cache
from kso_sidecar_agent.token_state import TokenState


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

REPORT_PATH = "/api/device-gateway/media/cache/report"

SHA256_RE = _re.compile(r"^[0-9a-fA-F]{64}$")

ALLOWED_ITEM_STATUSES = frozenset({
    "cached", "missing", "failed", "invalid_hash", "evicted",
})

FORBIDDEN_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
    "media_path", "creatives/",
})


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden(value: str, field: str) -> None:
    lower = value.lower()
    for fb in FORBIDDEN_SUBSTRINGS:
        if fb in lower:
            raise ValueError(f"Field '{field}' contains forbidden substring '{fb}'")


def _validate_uuid(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}: must be a string, got {type(value).__name__}")
    try:
        _UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"{field}: '{value}' is not a valid UUID")
    return value


# ══════════════════════════════════════════════════════════════════════
# Data classes
# ══════════════════════════════════════════════════════════════════════

@dataclass
class MediaCacheReportItem:
    """Single item in a cache report. Backend schema: CacheReportItem."""

    manifest_item_id: str
    status: str                            # cached|missing|failed|invalid_hash|evicted
    reported_sha256: Optional[str] = None  # 64 hex, required if status=cached
    file_size_bytes: Optional[int] = None
    cached_at: Optional[str] = None        # ISO8601
    error_code: Optional[str] = None       # max 64 chars
    message: Optional[str] = None          # max 512 chars
    details_json: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d: dict[str, Any] = {
            "manifest_item_id": self.manifest_item_id,
            "status": self.status,
        }
        if self.reported_sha256 is not None:
            d["reported_sha256"] = self.reported_sha256
        if self.file_size_bytes is not None:
            d["file_size_bytes"] = self.file_size_bytes
        if self.cached_at is not None:
            d["cached_at"] = self.cached_at
        if self.error_code is not None:
            d["error_code"] = self.error_code
        if self.message is not None:
            d["message"] = self.message
        if self.details_json:
            d["details_json"] = self.details_json
        return d


@dataclass
class MediaCacheReportPayload:
    """Full cache report payload. Backend schema: MediaCacheReportRequest."""

    manifest_version_id: str
    manifest_hash: str                     # 64 hex
    items: list[MediaCacheReportItem] = field(default_factory=list)
    device_reported_at: Optional[str] = None
    details_json: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d: dict[str, Any] = {
            "manifest_version_id": self.manifest_version_id,
            "manifest_hash": self.manifest_hash,
            "items": [item.as_dict() for item in self.items],
        }
        if self.device_reported_at is not None:
            d["device_reported_at"] = self.device_reported_at
        if self.details_json:
            d["details_json"] = self.details_json
        return d

    def safe_summary(self) -> dict:
        """Return metadata only — no full items list, no secrets."""
        cached = sum(1 for i in self.items if i.status == "cached")
        missing = sum(1 for i in self.items if i.status == "missing")
        failed = sum(1 for i in self.items if i.status == "failed")
        invalid_hash = sum(1 for i in self.items if i.status == "invalid_hash")
        return {
            "manifest_version_id": self.manifest_version_id[:12] + "...",
            "items_total": len(self.items),
            "cached": cached,
            "missing": missing,
            "failed": failed,
            "invalid_hash": invalid_hash,
        }


@dataclass
class MediaCacheReportResult:
    """Result of sending a cache report. Backend schema: MediaCacheReportResponse."""

    accepted: bool
    manifest_version_id: str
    total_items: int = 0
    cached_count: int = 0
    missing_count: int = 0
    failed_count: int = 0
    invalid_hash_count: int = 0
    sent_at: Optional[float] = None
    backend_status: str = ""

    def safe_summary(self) -> dict:
        """Return metadata only — no secrets, no full IDs."""
        return {
            "accepted": self.accepted,
            "manifest_version_id": self.manifest_version_id[:12] + "...",
            "total_items": self.total_items,
            "cached_count": self.cached_count,
            "missing_count": self.missing_count,
            "failed_count": self.failed_count,
            "invalid_hash_count": self.invalid_hash_count,
            "sent_at": self.sent_at,
        }


# ══════════════════════════════════════════════════════════════════════
# Payload builder
# ══════════════════════════════════════════════════════════════════════

def build_media_cache_report_payload(
    root,
    manifest_data: Optional[dict] = None,
    now: Optional[str] = None,
) -> MediaCacheReportPayload:
    """Build a safe cache report payload from local manifest + media cache status.

    Args:
        root: Agent root path (str or Path).
        manifest_data: Optional pre-loaded manifest dict. If None, reads from disk.
        now: ISO8601 timestamp.

    Returns:
        MediaCacheReportPayload ready to send. Never contains secrets/paths.

    Raises:
        FileNotFoundError: Manifest missing.
        ValueError: Manifest invalid, item validation failed.
    """
    from pathlib import Path
    root = Path(root)

    if manifest_data is None:
        manifest_data = _manifest_store.read_current_manifest(root)

    if not isinstance(manifest_data, dict):
        raise ValueError("Manifest data must be a dict")

    manifest_version_id = manifest_data.get("manifest_version_id", "")
    _validate_uuid(manifest_version_id, "manifest_version_id")

    manifest_hash = manifest_data.get("manifest_hash", "")
    if not isinstance(manifest_hash, str) or not SHA256_RE.match(manifest_hash):
        raise ValueError("manifest_hash must be 64 hex chars")

    items = manifest_data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("manifest.items must be a list")

    report_items: list[MediaCacheReportItem] = []

    for item in items:
        item_id = item.get("manifest_item_id", "")
        if not item_id:
            raise ValueError("manifest_item_id missing in manifest item")
        _validate_uuid(item_id, f"manifest_item_id")

        filename = item.get("filename", "")
        if not filename:
            raise ValueError(f"filename missing for item {item_id}")

        _check_forbidden(filename, f"filename for {item_id}")

        # Verify file in cache
        verify = _media_cache.verify_media_file(root, item)

        if verify["status"] == "ok":
            status = "cached"
            sha = item.get("sha256", "")
            actual_size = (root / _media_cache.MEDIA_CURRENT_DIR / filename).stat().st_size
            report_items.append(MediaCacheReportItem(
                manifest_item_id=item_id,
                status=status,
                reported_sha256=sha,
                file_size_bytes=actual_size,
                cached_at=None,
            ))
        elif verify["status"] == "missing":
            report_items.append(MediaCacheReportItem(
                manifest_item_id=item_id,
                status="missing",
            ))
        elif verify["status"] == "invalid":
            report_items.append(MediaCacheReportItem(
                manifest_item_id=item_id,
                status="invalid_hash",
                error_code="invalid_hash",
                message="File exists but sha256 does not match manifest",
            ))
        else:
            report_items.append(MediaCacheReportItem(
                manifest_item_id=item_id,
                status="failed",
                error_code=verify.get("status", "unknown"),
                message=verify.get("error", "Unknown error"),
            ))

    # Security scan on all items
    for ri in report_items:
        _check_forbidden(ri.manifest_item_id, "report_item.manifest_item_id")
        if ri.reported_sha256:
            _check_forbidden(ri.reported_sha256, "report_item.reported_sha256")
        if ri.error_code:
            _check_forbidden(ri.error_code, "report_item.error_code")
        if ri.message:
            _check_forbidden(ri.message, "report_item.message")

    payload = MediaCacheReportPayload(
        manifest_version_id=manifest_version_id,
        manifest_hash=manifest_hash,
        items=report_items,
        device_reported_at=now,
    )

    return payload


# ══════════════════════════════════════════════════════════════════════
# Media Cache Report Client
# ══════════════════════════════════════════════════════════════════════

class MediaCacheReportClient:
    """Sends media cache reports to backend. Token stays in memory only.

    Does NOT implement retry (that will be a separate step).
    Never logs Authorization header or request/response body.
    """

    REPORT_PATH = REPORT_PATH

    def __init__(
        self,
        http_client: SafeHttpClient,
        logger: Optional[Any] = None,
    ) -> None:
        self._http = http_client
        self._log = logger

    def send_report(
        self,
        token_state: TokenState,
        payload: MediaCacheReportPayload,
        now: Optional[float] = None,
    ) -> MediaCacheReportResult:
        """Send a cache report to backend.

        Args:
            token_state: Valid TokenState with access_token.
            payload: MediaCacheReportPayload (built by build_media_cache_report_payload).
            now: Current timestamp (defaults to time.time()).

        Returns:
            MediaCacheReportResult with accepted flag and counts.

        Raises:
            ValueError: Token invalid, payload validation failed.
            HttpClientError: HTTP-level failure.
        """
        if now is None:
            now = _time.time()

        # Validate token (NOT retryable — no HTTP request)
        if not token_state.is_valid(now=now):
            raise ValueError("Token is missing or expired — cannot send cache report")

        # Validate payload
        _validate_uuid(payload.manifest_version_id, "payload.manifest_version_id")
        if not isinstance(payload.manifest_hash, str) or not SHA256_RE.match(payload.manifest_hash):
            raise ValueError("payload.manifest_hash must be 64 hex chars")
        if not payload.items:
            raise ValueError("payload.items must not be empty")
        if len(payload.items) > 1000:
            raise ValueError("payload.items must not exceed 1000")

        for item in payload.items:
            _validate_uuid(item.manifest_item_id, "report_item.manifest_item_id")
            if item.status not in ALLOWED_ITEM_STATUSES:
                raise ValueError(
                    f"report_item.status '{item.status}' not allowed. "
                    f"Allowed: {', '.join(sorted(ALLOWED_ITEM_STATUSES))}"
                )
            if item.status == "cached" and not item.reported_sha256:
                raise ValueError(
                    f"reported_sha256 required for cached item {item.manifest_item_id}"
                )
            if item.reported_sha256:
                if not SHA256_RE.match(item.reported_sha256):
                    raise ValueError(
                        f"reported_sha256 must be 64 hex chars for item {item.manifest_item_id}"
                    )
            if item.file_size_bytes is not None and item.file_size_bytes < 0:
                raise ValueError(
                    f"file_size_bytes must be >= 0 for item {item.manifest_item_id}"
                )

        # Build JSON body
        body = payload.as_dict()

        # Security scan on body dict
        self._scan_body(body)

        auth_header = token_state.authorization_header(now=now)
        headers = {"Authorization": auth_header}

        try:
            resp: HttpResponse = self._http.post_json(
                self.REPORT_PATH, payload=body, headers=headers,
            )
        except HttpClientError as e:
            if self._log:
                self._log.log(
                    level="error",
                    event="cache_report_failed",
                    message=f"Cache report failed: {e}",
                )
            raise

        return self._parse_response(resp, now)

    def _scan_body(self, data: Any, path: str = "$") -> None:
        """Recursively check all keys and string values for forbidden substrings."""
        if isinstance(data, dict):
            for key, value in data.items():
                full_path = f"{path}.{key}"
                _check_forbidden(key, full_path)
                if isinstance(value, str):
                    _check_forbidden(value, full_path)
                elif isinstance(value, (dict, list)):
                    self._scan_body(value, full_path)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                full_path = f"{path}[{i}]"
                if isinstance(item, str):
                    _check_forbidden(item, full_path)
                elif isinstance(item, (dict, list)):
                    self._scan_body(item, full_path)

    def _parse_response(
        self, resp: HttpResponse, now: float,
    ) -> MediaCacheReportResult:
        """Parse and validate the cache report response."""
        body = resp.json_body

        if not isinstance(body, dict):
            raise HttpClientError(
                status_code=resp.status_code,
                message="Invalid cache report response: expected JSON object",
                retryable=False,
            )

        accepted = body.get("status") == "ok"

        result = MediaCacheReportResult(
            accepted=accepted,
            manifest_version_id=str(body.get("manifest_version_id", "")),
            total_items=body.get("total_items", 0),
            cached_count=body.get("cached_count", 0),
            missing_count=body.get("missing_count", 0),
            failed_count=body.get("failed_count", 0),
            invalid_hash_count=body.get("invalid_hash_count", 0),
            sent_at=now,
            backend_status=body.get("status", ""),
        )

        if self._log:
            self._log.log(
                level="info",
                event="cache_report_sent",
                message="Cache report sent successfully",
                extra=result.safe_summary(),
            )

        return result
