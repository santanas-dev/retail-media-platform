"""KSO Sidecar Device Auth Client — with optional retry/backoff.

Performs POST /api/device-gateway/auth/token and returns a memory-only TokenState.
When retry_manager is provided, transient errors (429/5xx/network/timeout) are retried
with exponential backoff + jitter. Non-transient errors (401/403/422/…) are never retried.

Never logs, prints, or writes the access_token or device_secret.
"""

import time as _time
from typing import Any, Callable, Optional, Tuple

from kso_sidecar_agent.http_client import HttpClientError, HttpResponse, SafeHttpClient
from kso_sidecar_agent.token_state import TokenState

# ── Secret reader type ─────────────────────────────────────────────────

SecretReader = Callable[[], str]
"""A callable that returns the device_secret string (or raises on failure)."""


# ══════════════════════════════════════════════════════════════════════
# Device Auth Client
# ══════════════════════════════════════════════════════════════════════

class DeviceAuthClient:
    """Orchestrates device auth with optional retry/backoff. Token stays in memory only.

    When retry_manager is None (default): single auth call.
    When retry_manager is provided: retries on transient errors with exponential backoff.
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
        # Track last attempt count (set by authenticate())
        self.last_attempts: int = 0

    def authenticate(
        self,
        now: Optional[float] = None,
        retry_manager: Optional[Any] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> TokenState:
        """Perform device auth. Returns TokenState (memory-only).

        Args:
            now: Current unix timestamp (defaults to time.time()).
            retry_manager: Optional RetryBackoffManager. If None, single call only.
            sleep_fn: Sleep function for delays (defaults to time.sleep).
                      Override in tests to avoid real delays.

        Raises:
            ValueError: config missing required fields.
            RuntimeError: secret store returned empty secret.
            HttpClientError: HTTP-level failure (from SafeHttpClient).

        Returns:
            TokenState with access_token in memory only. Sets self.last_attempts.
        """
        self.last_attempts = 0

        # ── 1. Read inputs (NO retry — these are config errors) ──────
        device_code = self._config.get("device_code", "")
        if not device_code:
            raise ValueError("device_code is missing from config")

        device_secret = self._read_secret()
        if not device_secret:
            raise RuntimeError("Device secret is empty — store not configured or secret missing")

        # ── 2. Build payload (never logged) ──────────────────────────
        payload = {
            "device_code": device_code,
            "device_secret": device_secret,
        }

        # ── 3. HTTP call — with optional retry ──────────────────────
        _sleep = sleep_fn or _time.sleep
        max_attempts = retry_manager.policy.max_attempts if retry_manager else 1
        last_error: Optional[HttpClientError] = None

        for attempt in range(1, max_attempts + 1):
            self.last_attempts = attempt
            try:
                resp: HttpResponse = self._http.post_json(self.AUTH_PATH, payload)
                break  # success
            except HttpClientError as e:
                last_error = e
                if retry_manager is None:
                    self._log_failure()
                    raise

                decision = retry_manager.next_decision(attempt, e)
                if not decision.should_retry:
                    self._log_failure()
                    raise

                if self._log:
                    self._log.log(
                        level="warning",
                        event="device_auth_retry",
                        message=f"Auth attempt {attempt} failed, retrying in {decision.delay_sec:.1f}s",
                        extra={
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "delay_sec": round(decision.delay_sec, 1),
                            "reason": decision.reason,
                        },
                    )
                _sleep(decision.delay_sec)
        else:
            # Exhausted all retry attempts
            self._log_failure()
            assert last_error is not None
            raise last_error

        # ── 4. Build TokenState (NO retry — response is final) ──────
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
                message=f"Device authenticated successfully (attempts: {self.last_attempts})",
                extra=token_state.safe_summary(now=now),
            )

        return token_state

    # ── Internal ────────────────────────────────────────────────────

    def _log_failure(self) -> None:
        if self._log:
            self._log.log(
                level="error",
                event="device_auth_failed",
                message=f"Device authentication failed (attempts: {self.last_attempts})",
            )
