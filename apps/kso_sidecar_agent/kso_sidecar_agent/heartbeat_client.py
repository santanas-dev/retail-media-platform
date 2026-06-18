"""Heartbeat Client for KSO Sidecar Agent.

Sends heartbeat to backend via POST /api/device-gateway/heartbeat.
Validates payload before sending — no forbidden substrings.

Does NOT implement heartbeat loop (that will be a separate step).
Never logs Authorization header, request/response body, or secrets.
"""

import time as _time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from kso_sidecar_agent.http_client import HttpClientError, HttpResponse, SafeHttpClient
from kso_sidecar_agent.retry_backoff import BackoffPolicy, RetryBackoffManager, execute_with_retries
from kso_sidecar_agent.token_state import TokenState

# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

# Must match backend HEARTBEAT_STATUSES
ALLOWED_HEARTBEAT_STATUSES = frozenset({"ok", "warning", "error"})

FORBIDDEN_PAYLOAD_SUBSTRINGS = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "authorization", "bearer",
    "device_secret", "access_token",
]

MANIFEST_HASH_RE = r"^[0-9a-fA-F]{64}$"  # used in validation


# ══════════════════════════════════════════════════════════════════════
# Payload
# ══════════════════════════════════════════════════════════════════════

@dataclass
class HeartbeatPayload:
    """Validated heartbeat payload. Matches DeviceHeartbeatRequest schema."""

    status: str = "ok"
    message: Optional[str] = None
    device_time: Optional[str] = None
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    storage_free_mb: Optional[int] = None
    cache_items_count: Optional[int] = None
    current_manifest_hash: Optional[str] = None
    details_json: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_heartbeat_payload(self)

    def to_dict(self) -> dict:
        """Return payload as dict for JSON serialization. Omits None values."""
        result: dict = {"status": self.status}
        if self.message is not None:
            result["message"] = self.message
        if self.device_time is not None:
            result["device_time"] = self.device_time
        if self.app_version is not None:
            result["app_version"] = self.app_version
        if self.os_version is not None:
            result["os_version"] = self.os_version
        if self.storage_free_mb is not None:
            result["storage_free_mb"] = self.storage_free_mb
        if self.cache_items_count is not None:
            result["cache_items_count"] = self.cache_items_count
        if self.current_manifest_hash is not None:
            result["current_manifest_hash"] = self.current_manifest_hash
        if self.details_json:
            result["details_json"] = self.details_json
        return result


def _check_forbidden(value: str, field: str) -> None:
    lower = value.lower()
    for forbidden in FORBIDDEN_PAYLOAD_SUBSTRINGS:
        if forbidden in lower:
            raise ValueError(
                f"Heartbeat field '{field}' contains forbidden substring '{forbidden}'"
            )


def _validate_heartbeat_payload(p: HeartbeatPayload) -> None:
    """Validate all payload fields. Raises ValueError on failure."""
    # Status
    if not p.status or not isinstance(p.status, str):
        raise ValueError("status is required")
    if p.status not in ALLOWED_HEARTBEAT_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(ALLOWED_HEARTBEAT_STATUSES)}, "
            f"got '{p.status}'"
        )

    # Message (optional, max 200)
    if p.message is not None:
        if not isinstance(p.message, str):
            raise ValueError("message must be a string")
        if len(p.message) > 200:
            raise ValueError(f"message too long: {len(p.message)} (max 200)")
        _check_forbidden(p.message, "message")

    # Versions (optional, max 128)
    for field, val in [("app_version", p.app_version), ("os_version", p.os_version)]:
        if val is not None:
            if not isinstance(val, str):
                raise ValueError(f"{field} must be a string")
            if len(val) > 128:
                raise ValueError(f"{field} too long: {len(val)} (max 128)")

    # Storage (optional, >= 0)
    if p.storage_free_mb is not None:
        if not isinstance(p.storage_free_mb, int) or p.storage_free_mb < 0:
            raise ValueError(f"storage_free_mb must be >= 0, got {p.storage_free_mb}")

    # Cache count (optional, >= 0)
    if p.cache_items_count is not None:
        if not isinstance(p.cache_items_count, int) or p.cache_items_count < 0:
            raise ValueError(f"cache_items_count must be >= 0, got {p.cache_items_count}")

    # Manifest hash (optional, 64 hex)
    if p.current_manifest_hash is not None:
        if not isinstance(p.current_manifest_hash, str):
            raise ValueError("current_manifest_hash must be a string")
        if len(p.current_manifest_hash) != 64:
            raise ValueError(
                f"current_manifest_hash must be 64 hex chars, got {len(p.current_manifest_hash)}"
            )
        if not all(c in "0123456789abcdef" for c in p.current_manifest_hash.lower()):
            raise ValueError("current_manifest_hash must be 64 hex characters")

    # Details (optional, no forbidden)
    if p.details_json:
        if not isinstance(p.details_json, dict):
            raise ValueError("details_json must be a dict")
        _validate_details_safe(p.details_json)


def _validate_details_safe(details: dict, path: str = "") -> None:
    """Recursively check details_json for forbidden keys/values."""
    for key, value in details.items():
        full_key = f"{path}.{key}" if path else key
        _check_forbidden(key, f"details_json key '{full_key}'")
        if isinstance(value, str):
            _check_forbidden(value, f"details_json value '{full_key}'")
        if isinstance(value, dict):
            _validate_details_safe(value, full_key)


# ══════════════════════════════════════════════════════════════════════
# Result
# ══════════════════════════════════════════════════════════════════════

@dataclass
class HeartbeatResult:
    """Safe heartbeat result. Never exposes token or secrets."""

    status: str = "sent"  # sent | error
    backend_status: Optional[str] = None
    heartbeat_id: Optional[str] = None
    device_id: Optional[str] = None

    def safe_summary(self) -> dict:
        return {
            "status": self.status,
            "backend_status": self.backend_status,
            "heartbeat_id": self.heartbeat_id,
            "device_id": self.device_id,
        }


# ══════════════════════════════════════════════════════════════════════
# Client
# ══════════════════════════════════════════════════════════════════════

class HeartbeatClient:
    """Sends heartbeat to backend. Token stays in memory only.

    Supports optional retry/backoff via RetryBackoffManager.
    When retry_manager is None (default): single heartbeat call only.
    When retry_manager is provided: retries transient errors (429/5xx/network)
    with exponential backoff + jitter.
    """

    HEARTBEAT_PATH = "/api/device-gateway/heartbeat"

    def __init__(
        self,
        http_client: SafeHttpClient,
        retry_manager: Optional[RetryBackoffManager] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        logger: Optional[Any] = None,
    ) -> None:
        self._http = http_client
        self._retry = retry_manager
        self._sleep = sleep_fn
        self._log = logger
        self.last_attempts: int = 0
        """Number of attempts from most recent send_heartbeat call."""

    def send_heartbeat(
        self,
        token_state: TokenState,
        payload: HeartbeatPayload,
        now: Optional[float] = None,
    ) -> HeartbeatResult:
        """Send a single heartbeat (with optional retry). Returns safe HeartbeatResult.

        Args:
            token_state: Valid TokenState with access_token.
            payload: Validated HeartbeatPayload.
            now: Current timestamp (defaults to time.time()).

        Returns:
            HeartbeatResult with status and backend info.

        Raises:
            ValueError: Token invalid, payload invalid.
            HttpClientError: HTTP-level failure (exhausted retries or non-retryable).
        """
        if now is None:
            now = _time.time()

        self.last_attempts = 0

        # ── Validate token (NOT retryable) ─────────────────────────
        if not token_state.is_valid(now=now):
            raise ValueError("Token is missing or expired — cannot send heartbeat")

        # ── Build headers (NOT retryable) ──────────────────────────
        auth_header = token_state.authorization_header(now=now)
        headers = {"Authorization": auth_header}

        # ── Build payload dict (NOT retryable) ─────────────────────
        body = payload.to_dict()

        # ── Send (with optional retry) ─────────────────────────────
        if self._retry is not None:
            return self._send_with_retry(body, headers)
        else:
            return self._send_once(body, headers)

    def _send_once(self, body: dict, headers: dict) -> HeartbeatResult:
        """Send a single heartbeat (no retry)."""
        self.last_attempts = 1
        try:
            resp: HttpResponse = self._http.post_json(self.HEARTBEAT_PATH, body, headers=headers)
        except HttpClientError:
            if self._log:
                self._log.log(
                    level="error",
                    event="heartbeat_failed",
                    message="Heartbeat request failed",
                )
            raise

        return self._parse_response(resp)

    def _send_with_retry(self, body: dict, headers: dict) -> HeartbeatResult:
        """Send heartbeat with retry/backoff."""
        last_error: Optional[HttpClientError] = None
        max_attempts = self._retry.policy.max_attempts

        try:
            resp = execute_with_retries(
                operation=lambda: self._http.post_json(self.HEARTBEAT_PATH, body, headers=headers),
                manager=self._retry,
                sleep_fn=self._sleep,
            )
            self.last_attempts = max_attempts  # not accurate per-attempt, but ok
        except HttpClientError as e:
            last_error = e
            self.last_attempts = max_attempts
        else:
            return self._parse_response(resp)

        # Exhausted or non-retryable
        if self._log:
            self._log.log(
                level="error",
                event="heartbeat_failed",
                message="Heartbeat request failed after retries",
            )
        raise last_error

    def _parse_response(self, resp: HttpResponse) -> HeartbeatResult:
        """Parse heartbeat response into HeartbeatResult. Safe: no token/secrets."""
        resp_body = resp.json_body
        heartbeat_id = str(resp_body.get("id", "")) if isinstance(resp_body, dict) else None
        device_id = str(resp_body.get("gateway_device_id", "")) if isinstance(resp_body, dict) else None
        backend_status = resp_body.get("status") if isinstance(resp_body, dict) else None

        result = HeartbeatResult(
            status="sent",
            backend_status=backend_status,
            heartbeat_id=heartbeat_id,
            device_id=device_id,
        )

        if self._log:
            self._log.log(
                level="info",
                event="heartbeat_sent",
                message="Heartbeat sent successfully",
                extra=result.safe_summary(),
            )

        return result
