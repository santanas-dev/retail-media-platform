"""KSO Sidecar Device Auth Client — base (no retry/backoff).

Performs a single POST /api/device-gateway/auth/token call
and returns a memory-only TokenState.

Never logs, prints, or writes the access_token or device_secret.
"""

from typing import Any, Callable, Optional

from kso_sidecar_agent.http_client import HttpClientError, HttpResponse, SafeHttpClient
from kso_sidecar_agent.token_state import TokenState


# ── Secret reader type ─────────────────────────────────────────────────

SecretReader = Callable[[], str]
"""A callable that returns the device_secret string (or raises on failure).

Examples:
  - lambda: secret_store.read_secret(root, dev_secret_store=True)
  - production_secret_reader (future)
"""


# ══════════════════════════════════════════════════════════════════════
# Device Auth Client
# ══════════════════════════════════════════════════════════════════════

class DeviceAuthClient:
    """Orchestrates a single device auth call. Token stays in memory only.

    Does NOT implement retry/backoff or token refresh.
    Those will be added in later steps.
    """

    AUTH_PATH = "/api/device-gateway/auth/token"

    def __init__(
        self,
        http_client: SafeHttpClient,
        config: dict,
        secret_reader: SecretReader,
        logger: Optional[Any] = None,
    ) -> None:
        """Create a DeviceAuthClient.

        Args:
            http_client: SafeHttpClient instance (already configured).
            config: Validated config dict from local_config.read_config().
            secret_reader: Callable that returns device_secret as a string.
            logger: Optional safe_logger (or any object with .log()).
        """
        self._http = http_client
        self._config = config
        self._read_secret = secret_reader
        self._log = logger

    def authenticate(self, now: Optional[float] = None) -> TokenState:
        """Perform a single device auth call. Returns TokenState (memory-only).

        Raises:
            ValueError: config missing required fields.
            RuntimeError: secret store returned empty secret.
            HttpClientError: HTTP-level failure (from SafeHttpClient).
        """
        # ── Read inputs ──────────────────────────────────────────────
        device_code = self._config.get("device_code", "")
        if not device_code:
            raise ValueError("device_code is missing from config")

        device_secret = self._read_secret()
        if not device_secret:
            raise RuntimeError("Device secret is empty — store not configured or secret missing")

        # ── Build payload (never logged) ────────────────────────────
        payload = {
            "device_code": device_code,
            "device_secret": device_secret,
        }

        # ── Call backend ─────────────────────────────────────────────
        try:
            resp: HttpResponse = self._http.post_json(self.AUTH_PATH, payload)
        except HttpClientError:
            # Re-raise — error message already safe (no body/secret)
            if self._log:
                self._log.log(
                    level="error",
                    event="device_auth_failed",
                    message="Device authentication failed",
                )
            raise

        # ── Build TokenState (memory only) ───────────────────────────
        try:
            token_state = TokenState.from_auth_response(resp.json_body, now=now)
        except (ValueError, TypeError, KeyError) as e:
            raise HttpClientError(
                status_code=resp.status_code,
                message=f"Invalid auth response: {e}",
                retryable=False,
            ) from None

        if self._log:
            self._log.log(
                level="info",
                event="device_authenticated",
                message="Device authenticated successfully",
                extra=token_state.safe_summary(now=now),
            )

        return token_state
