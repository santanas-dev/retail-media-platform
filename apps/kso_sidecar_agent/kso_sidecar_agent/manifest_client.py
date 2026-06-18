"""Manifest Client for KSO Sidecar Agent.

Fetches manifest from backend via:
  GET /api/device-gateway/manifest/current
  GET /api/device-gateway/manifest/{manifest_version_id}

Does NOT write manifest to disk (that will be a separate step).
Does NOT implement retry (that will be a separate step).
Never logs Authorization header, response body, or secrets.
"""

import re as _re
import time as _time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID as _UUID

from kso_sidecar_agent.http_client import HttpClientError, HttpResponse, SafeHttpClient
from kso_sidecar_agent.token_state import TokenState

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_MANIFEST_SUBSTRINGS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
})

_MANIFEST_HASH_RE = _re.compile(r"^[0-9a-fA-F]{64}$")
_PATH_TRAVERSAL_RE = _re.compile(r"\.\.|[\\]|^[A-Za-z]:")  # ../, backslash, C:\


# ══════════════════════════════════════════════════════════════════════
# Validation helpers
# ══════════════════════════════════════════════════════════════════════

def _check_forbidden(value: str, field_path: str) -> None:
    """Raise ValueError if value contains any forbidden substring."""
    lower = value.lower()
    for forbidden in FORBIDDEN_MANIFEST_SUBSTRINGS:
        if forbidden in lower:
            raise ValueError(
                f"Manifest field '{field_path}' contains forbidden substring '{forbidden}'"
            )


def _validate_sha256_hex(value: str, field_path: str) -> None:
    """Validate a sha256 hex string (64 hex chars)."""
    if not isinstance(value, str):
        raise ValueError(f"Manifest field '{field_path}': sha256 must be a string")
    if not _MANIFEST_HASH_RE.match(value):
        raise ValueError(
            f"Manifest field '{field_path}': must be 64 hex chars, got {len(value)}"
        )


def _validate_path_safe(value: str, field_path: str) -> None:
    """Validate a filename/object_key has no path traversal."""
    if not isinstance(value, str):
        raise ValueError(f"Manifest field '{field_path}': must be a string")
    if value.startswith("/"):
        raise ValueError(f"Manifest field '{field_path}': must not be absolute path")
    if _PATH_TRAVERSAL_RE.search(value):
        raise ValueError(
            f"Manifest field '{field_path}': contains path traversal"
        )


def _validate_manifest_item(item: dict, idx: int) -> None:
    """Validate a single manifest item. Raises ValueError."""
    if not isinstance(item, dict):
        raise ValueError(f"Manifest item[{idx}] must be an object, got {type(item).__name__}")

    # id (optional, UUID if present)
    if "id" in item:
        rid = item["id"]
        if not isinstance(rid, str):
            raise ValueError(f"Manifest item[{idx}].id must be a string")
        try:
            _UUID(rid)
        except (ValueError, AttributeError):
            raise ValueError(f"Manifest item[{idx}].id is not a valid UUID: {rid}")

    # sha256 (optional, 64 hex if present)
    if "sha256" in item:
        _validate_sha256_hex(item["sha256"], f"item[{idx}].sha256")

    # manifest_hash (optional, 64 hex if present; alternative field name)
    if "manifest_hash" in item:
        _validate_sha256_hex(item["manifest_hash"], f"item[{idx}].manifest_hash")

    # duration_ms (optional, >= 0 if present)
    if "duration_ms" in item:
        d = item["duration_ms"]
        if not isinstance(d, int) or d < 0:
            raise ValueError(
                f"Manifest item[{idx}].duration_ms must be >= 0, got {d!r}"
            )

    # order / loop_position / spot_position (optional, >= 0 if present)
    for ord_field in ("order", "loop_position", "spot_position"):
        if ord_field in item:
            v = item[ord_field]
            if not isinstance(v, int) or v < 0:
                raise ValueError(
                    f"Manifest item[{idx}].{ord_field} must be >= 0, got {v!r}"
                )

    # media_path / object_key / filename (path safety)
    for path_field in ("media_path", "object_key", "filename", "name"):
        if path_field in item:
            fp = item[path_field]
            if isinstance(fp, str) and fp:
                _validate_path_safe(fp, f"item[{idx}].{path_field}")

    # Forbidden keys/values in item
    for key, value in item.items():
        _check_forbidden(key, f"item[{idx}].key '{key}'")
        if isinstance(value, str):
            _check_forbidden(value, f"item[{idx}].{key}")


def _validate_manifest_body(body: dict) -> None:
    """Validate the full manifest response body. Raises ValueError."""
    if not isinstance(body, dict):
        raise ValueError("Manifest response must be a JSON object")

    # Check top-level forbidden keys
    for key in body:
        _check_forbidden(key, f"top-level key '{key}'")
        if isinstance(body[key], str):
            _check_forbidden(body[key], f"top-level value '{key}'")

    # manifest_version_id (UUID, if present)
    if "manifest_version_id" in body and body["manifest_version_id"] is not None:
        mvid = body["manifest_version_id"]
        if not isinstance(mvid, str):
            raise ValueError("manifest_version_id must be a string")
        try:
            _UUID(mvid)
        except (ValueError, AttributeError):
            raise ValueError(f"manifest_version_id is not a valid UUID: {mvid}")

    # manifest_hash (optional, 64 hex if present; also checked at top-level)
    if "manifest_hash" in body and body["manifest_hash"] is not None:
        _validate_sha256_hex(body["manifest_hash"], "manifest_hash")

    # manifest_items (optional list from /manifest/{id})
    items = body.get("manifest_items")
    # manifest (dict, from /manifest/current — might contain items list)
    manifest_data = body.get("manifest")
    if isinstance(manifest_data, dict):
        # /manifest/current wrapped shape: manifest may have its own items
        inner_items = manifest_data.get("items")
        if isinstance(inner_items, list):
            _validate_items_list(inner_items, "manifest.items")
        # Also check inner manifest for forbidden
        for key in manifest_data:
            _check_forbidden(key, f"manifest.key '{key}'")
    elif isinstance(items, list):
        _validate_items_list(items, "manifest_items")

    # If neither present, that's allowed (e.g., no_manifest)


def _validate_items_list(items: list, path: str) -> None:
    """Validate a list of manifest items."""
    if not isinstance(items, list):
        raise ValueError(f"Manifest {path} must be a list")
    for idx, item in enumerate(items):
        _validate_manifest_item(item, idx)


# ══════════════════════════════════════════════════════════════════════
# ManifestSnapshot
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ManifestSnapshot:
    """Holds the result of a manifest fetch.

    Never exposes secrets — safe_summary() returns only metadata.
    Manifest data is stored in memory only (no disk write on this step).
    """

    status: str = "served"            # served | not_modified | no_manifest | error
    manifest_version_id: Optional[str] = None
    manifest_hash: Optional[str] = None
    published_at: Optional[str] = None
    items: list = field(default_factory=list)
    fetched_at: Optional[float] = None
    source: str = "unknown"            # current | by_id
    not_modified: bool = False

    def safe_summary(self) -> dict:
        """Return metadata only — no manifest contents, no secrets."""
        return {
            "status": self.status,
            "manifest_version_id": self.manifest_version_id,
            "items_count": len(self.items) if self.items else 0,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
            "source": self.source,
            "not_modified": self.not_modified,
        }


# ══════════════════════════════════════════════════════════════════════
# ManifestClient
# ══════════════════════════════════════════════════════════════════════

class ManifestClient:
    """Fetches manifest from backend. Token stays in memory only.

    Does NOT implement retry (that will be a separate step).
    Does NOT write manifest to disk (that will be a separate step).
    Never logs Authorization header or response body.
    """

    CURRENT_PATH = "/api/device-gateway/manifest/current"

    def __init__(
        self,
        http_client: SafeHttpClient,
        logger: Optional[Any] = None,
    ) -> None:
        self._http = http_client
        self._log = logger

    # ── fetch_current ───────────────────────────────────────────────

    def fetch_current(
        self,
        token_state: TokenState,
        now: Optional[float] = None,
    ) -> ManifestSnapshot:
        """Fetch current manifest. Returns snapshot (memory only).

        Args:
            token_state: Valid TokenState with access_token.
            now: Current timestamp (defaults to time.time()).

        Returns:
            ManifestSnapshot with status and manifest items.

        Raises:
            ValueError: Token invalid, manifest validation failed.
            HttpClientError: HTTP-level failure.
        """
        if now is None:
            now = _time.time()

        # Validate token (NOT retryable)
        if not token_state.is_valid(now=now):
            raise ValueError("Token is missing or expired — cannot fetch manifest")

        auth_header = token_state.authorization_header(now=now)
        headers = {"Authorization": auth_header}

        try:
            resp: HttpResponse = self._http.get_json(self.CURRENT_PATH, headers=headers)
        except HttpClientError as e:
            if self._log:
                self._log.log(
                    level="error",
                    event="manifest_fetch_failed",
                    message=f"Manifest fetch failed: {e}",
                )
            raise

        return self._parse_current_response(resp, now)

    def _parse_current_response(self, resp: HttpResponse, now: float) -> ManifestSnapshot:
        """Parse the /manifest/current response into a ManifestSnapshot."""
        body = resp.json_body

        if not isinstance(body, dict):
            raise HttpClientError(
                status_code=resp.status_code,
                message="Invalid manifest response: expected JSON object",
                retryable=False,
            )

        st = body.get("status", "unknown")

        # not_modified or no_manifest
        if st == "not_modified":
            return ManifestSnapshot(
                status="not_modified",
                manifest_version_id=body.get("manifest_version_id"),
                manifest_hash=body.get("manifest_hash"),
                fetched_at=now,
                source="current",
                not_modified=True,
            )

        if st == "no_manifest":
            return ManifestSnapshot(
                status="no_manifest",
                fetched_at=now,
                source="current",
            )

        # served — validate and extract
        try:
            _validate_manifest_body(body)
        except ValueError as e:
            raise HttpClientError(
                status_code=resp.status_code,
                message=str(e),
                retryable=False,
            ) from None

        # Extract items from manifest field or top-level items
        manifest_data = body.get("manifest")
        items = []
        if isinstance(manifest_data, dict):
            inner = manifest_data.get("items")
            if isinstance(inner, list):
                items = inner

        snapshot = ManifestSnapshot(
            status="served",
            manifest_version_id=body.get("manifest_version_id"),
            manifest_hash=body.get("manifest_hash"),
            published_at=body.get("published_at"),
            items=items,
            fetched_at=now,
            source="current",
        )

        if self._log:
            self._log.log(
                level="info",
                event="manifest_fetched",
                message="Manifest fetched successfully",
                extra=snapshot.safe_summary(),
            )

        return snapshot

    # ── fetch_by_id ──────────────────────────────────────────────────

    def fetch_by_id(
        self,
        token_state: TokenState,
        manifest_version_id: str,
        now: Optional[float] = None,
    ) -> ManifestSnapshot:
        """Fetch a specific manifest by version ID. Returns snapshot (memory only).

        Args:
            token_state: Valid TokenState with access_token.
            manifest_version_id: UUID of the manifest version.
            now: Current timestamp (defaults to time.time()).

        Returns:
            ManifestSnapshot with status and manifest items.

        Raises:
            ValueError: Token invalid, invalid manifest_version_id, manifest validation failed.
            HttpClientError: HTTP-level failure.
        """
        if now is None:
            now = _time.time()

        # Validate token
        if not token_state.is_valid(now=now):
            raise ValueError("Token is missing or expired — cannot fetch manifest")

        # Validate manifest_version_id
        if not manifest_version_id or not isinstance(manifest_version_id, str):
            raise ValueError(
                f"manifest_version_id must be a non-empty string, got {manifest_version_id!r}"
            )
        try:
            _UUID(manifest_version_id)
        except (ValueError, AttributeError):
            raise ValueError(
                f"manifest_version_id is not a valid UUID: {manifest_version_id}"
            )

        auth_header = token_state.authorization_header(now=now)
        headers = {"Authorization": auth_header}

        by_id_path = f"/api/device-gateway/manifest/{manifest_version_id}"

        try:
            resp: HttpResponse = self._http.get_json(by_id_path, headers=headers)
        except HttpClientError as e:
            if self._log:
                self._log.log(
                    level="error",
                    event="manifest_fetch_failed",
                    message=f"Manifest fetch by ID failed: {e}",
                )
            raise

        return self._parse_by_id_response(resp, manifest_version_id, now)

    def _parse_by_id_response(
        self, resp: HttpResponse, manifest_version_id: str, now: float,
    ) -> ManifestSnapshot:
        """Parse the /manifest/{id} response into a ManifestSnapshot."""
        body = resp.json_body

        if not isinstance(body, dict):
            raise HttpClientError(
                status_code=resp.status_code,
                message="Invalid manifest response: expected JSON object",
                retryable=False,
            )

        try:
            _validate_manifest_body(body)
        except ValueError as e:
            raise HttpClientError(
                status_code=resp.status_code,
                message=str(e),
                retryable=False,
            ) from None

        # Extract items: either manifest_items (schema) or manifest (extra)
        items = body.get("manifest_items")
        if not isinstance(items, list):
            manifest_data = body.get("manifest")
            if isinstance(manifest_data, dict):
                inner = manifest_data.get("items")
                if isinstance(inner, list):
                    items = inner

        if not isinstance(items, list):
            items = []

        snapshot = ManifestSnapshot(
            status="served",
            manifest_version_id=manifest_version_id,
            manifest_hash=body.get("manifest_hash"),
            published_at=body.get("published_at"),
            items=items,
            fetched_at=now,
            source="by_id",
        )

        if self._log:
            self._log.log(
                level="info",
                event="manifest_fetched_by_id",
                message="Manifest fetched by ID successfully",
                extra=snapshot.safe_summary(),
            )

        return snapshot
