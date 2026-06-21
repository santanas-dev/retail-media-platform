"""KSO Sidecar — Gateway HTTP Client.

Real HTTP client implementing KsoGatewayClient protocol.
Uses SafeHttpClient (stdlib urllib) + existing TokenState auth.

Manifest: GET /api/device-gateway/manifest/current
Media:    GET /api/device-gateway/media/kso/{mediaRef}

Never logs URLs, auth headers, response bodies, or secrets.
"""

import json as _json
import re as _re
from typing import Any, Mapping, Optional

from kso_sidecar_agent.http_client import (
    HttpClientError,
    HttpBinaryResponse,
    HttpResponse,
    SafeHttpClient,
)
from kso_sidecar_agent.kso_manifest_media_sync import (
    KsoMediaDownloadResponse,
    STATUS_OK,
    STATUS_ERROR,
)
from kso_sidecar_agent.token_state import TokenState

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

MANIFEST_CURRENT_PATH = "/api/device-gateway/manifest/current"
KSO_MEDIA_PATH_PREFIX = "/api/device-gateway/media/kso/"

# Strict slot pattern
_SLOT_PATTERN = _re.compile(r"^media/current/slot-(\d{3})$")

_UNSAFE_IN_MEDIA_REF = ("..", "\\", "://", "http:", "https:", "file:",
                         "%2e", "%2f", "%2E", "%2F")


# ══════════════════════════════════════════════════════════════════════
# MediaRef validation
# ══════════════════════════════════════════════════════════════════════

def _validate_media_ref(media_ref: str) -> Optional[str]:
    """Validate mediaRef. Returns error message or None."""
    if not isinstance(media_ref, str) or not media_ref.strip():
        return "mediaRef must be a non-empty string"
    if media_ref.startswith("/"):
        return "mediaRef must not be absolute"
    lower = media_ref.lower()
    for unsafe in _UNSAFE_IN_MEDIA_REF:
        if unsafe in lower:
            return f"mediaRef contains unsafe pattern"
    if not _SLOT_PATTERN.match(media_ref):
        return f"mediaRef must match media/current/slot-NNN"
    return None


# ══════════════════════════════════════════════════════════════════════
# KSO Gateway HTTP Client
# ══════════════════════════════════════════════════════════════════════

class KsoGatewayHttpClient:
    """Real HTTP client for KSO manifest + media delivery.

    Wraps SafeHttpClient with KSO-specific endpoint logic.
    Implements the KsoGatewayClient protocol for sync_kso_manifest_and_media().

    Never logs/exposes: backend URL, auth header, mediaRef values, response body.
    """

    def __init__(
        self,
        http_client: SafeHttpClient,
        token_state: TokenState,
    ) -> None:
        """Create a KSO gateway HTTP client.

        Args:
            http_client: Configured SafeHttpClient instance.
            token_state: Authenticated TokenState (access_token in memory only).
        """
        self._http = http_client
        self._token = token_state

    # ── Auth header ────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        """Build Authorization header. Never logged/exposed."""
        return {"Authorization": f"Bearer {self._token.access_token}"}

    # ── Manifest ───────────────────────────────────────────────────

    def fetch_current_manifest(self) -> Mapping[str, Any]:
        """Fetch current KSO manifest from backend gateway.

        GET /api/device-gateway/manifest/current

        Returns:
            Parsed gateway response dict (including status, manifest, etc.).

        Raises:
            HttpClientError: On HTTP/network errors (401/403/404/5xx/timeout).
        """
        resp: HttpResponse = self._http.get_json(
            MANIFEST_CURRENT_PATH,
            headers=self._auth_headers(),
        )
        return resp.json_body

    # ── Media download ─────────────────────────────────────────────

    def download_kso_media(self, media_ref: str) -> KsoMediaDownloadResponse:
        """Download KSO media by safe mediaRef.

        GET /api/device-gateway/media/kso/{mediaRef}

        Validates mediaRef format BEFORE making HTTP request.
        Returns safe KsoMediaDownloadResponse — no URL, no auth in output.

        Args:
            media_ref: Safe slot reference, e.g. "media/current/slot-000".

        Returns:
            KsoMediaDownloadResponse with status, content_type, content_length, body.
        """
        # ── Validate mediaRef before HTTP ──────────────────────────
        error = _validate_media_ref(media_ref)
        if error:
            return KsoMediaDownloadResponse(
                status=STATUS_ERROR,
                content_type="",
                content_length=0,
                body=b"",
            )

        # ── Build path ─────────────────────────────────────────────
        path = f"{KSO_MEDIA_PATH_PREFIX}{media_ref}"

        try:
            bin_resp: HttpBinaryResponse = self._http.get_bytes(
                path,
                headers=self._auth_headers(),
                max_bytes=100 * 1024 * 1024,  # 100 MB
            )

            # Extract content-type from response headers
            content_type = ""
            for k, v in bin_resp.headers.items():
                if k.lower() == "content-type":
                    content_type = v
                    break

            return KsoMediaDownloadResponse(
                status=STATUS_OK,
                content_type=content_type,
                content_length=len(bin_resp.body_bytes),
                body=bin_resp.body_bytes,
            )

        except HttpClientError as e:
            # Safe error — no URL, no stacktrace
            return KsoMediaDownloadResponse(
                status=STATUS_ERROR,
                content_type="",
                content_length=0,
                body=b"",
            )
