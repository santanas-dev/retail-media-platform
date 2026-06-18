"""Runtime Config Client for KSO Sidecar Agent.

Fetches effective runtime config from backend via:
  GET /api/device-gateway/config/current

Supports ETag/304 (If-None-Match / ETag).
Does NOT write config to disk (that will be a separate step).
Never logs Authorization header, response body, or secrets.
"""

import time as _time
from dataclasses import dataclass, field
from typing import Any, Optional

from kso_sidecar_agent.http_client import (
    FORBIDDEN_HEADER_VALUES as _FORBIDDEN_VALUES,
    HttpClientError,
    HttpResponse,
    SafeHttpClient,
)
from kso_sidecar_agent.token_state import TokenState

# ══════════════════════════════════════════════════════════════════════
# Forbidden keys/values in runtime config
# ══════════════════════════════════════════════════════════════════════

FORBIDDEN_CONFIG_KEYS = frozenset({
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path", "credential", "cookie",
})


def _validate_config_safe(config: dict) -> None:
    """Raise ValueError if config has forbidden keys or values."""
    if not isinstance(config, dict):
        raise ValueError("runtime config must be a JSON object")

    for key in config:
        lower_key = key.lower()
        for forbidden in FORBIDDEN_CONFIG_KEYS:
            if forbidden in lower_key:
                raise ValueError(
                    f"runtime config contains forbidden key: '{key}'"
                )

    # Check string values recursively (shallow — only top-level values)
    for key, value in config.items():
        if isinstance(value, str):
            lower_val = value.lower()
            for forbidden in FORBIDDEN_CONFIG_KEYS:
                if forbidden in lower_val:
                    raise ValueError(
                        f"runtime config key '{key}' has forbidden substring '{forbidden}'"
                    )


# ══════════════════════════════════════════════════════════════════════
# RuntimeConfigSnapshot
# ══════════════════════════════════════════════════════════════════════

@dataclass
class RuntimeConfigSnapshot:
    """Holds the result of a runtime config fetch.

    Never exposes secrets — safe_summary() returns only metadata.
    Config is stored in memory only (no disk write on this step).
    """

    status: str = "updated"            # "updated" | "not_modified" | "error"
    config_hash: Optional[str] = None
    etag: Optional[str] = None
    generated_at: Optional[str] = None
    config: Optional[dict] = None      # Held in memory only
    fetched_at: Optional[float] = None
    not_modified: bool = False

    def safe_summary(self) -> dict:
        """Return metadata only — no config contents, no secrets."""
        return {
            "status": self.status,
            "config_hash": self.config_hash,
            "generated_at": self.generated_at,
            "fetched_at": self.fetched_at,
            "not_modified": self.not_modified,
            "config_present": self.config is not None,
            "config_keys_count": len(self.config) if self.config else 0,
        }


# ══════════════════════════════════════════════════════════════════════
# RuntimeConfigClient
# ══════════════════════════════════════════════════════════════════════

class RuntimeConfigClient:
    """Fetches runtime config from backend. Supports ETag/304.

    Does NOT implement retry (that will be a separate step).
    Does NOT write config to disk (that will be a separate step).
    Never logs Authorization header or response body.
    """

    CONFIG_PATH = "/api/device-gateway/config/current"

    def __init__(
        self,
        http_client: SafeHttpClient,
        logger: Optional[Any] = None,
    ) -> None:
        """Create a RuntimeConfigClient.

        Args:
            http_client: SafeHttpClient instance (already configured).
            logger: Optional safe_logger (or any object with .log()).
        """
        self._http = http_client
        self._log = logger

    def fetch_current(
        self,
        token_state: TokenState,
        etag: Optional[str] = None,
        now: Optional[float] = None,
    ) -> RuntimeConfigSnapshot:
        """Fetch current runtime config. Returns snapshot (memory only).

        Args:
            token_state: Valid TokenState with access_token.
            etag: Optional ETag from previous fetch (enables 304).
            now: Current timestamp (defaults to time.time()).

        Returns:
            RuntimeConfigSnapshot with status and (optionally) config.

        Raises:
            ValueError: Token invalid, config validation failed.
            HttpClientError: HTTP-level failure.
        """
        if now is None:
            now = _time.time()

        # ── 1. Validate token ────────────────────────────────────────
        if not token_state.is_valid(now=now):
            raise ValueError("Token is missing or expired — cannot fetch config")

        # ── 2. Build headers ─────────────────────────────────────────
        auth_header = token_state.authorization_header(now=now)
        headers = {"Authorization": auth_header}

        if etag:
            headers["If-None-Match"] = etag

        # ── 3. Call backend ──────────────────────────────────────────
        try:
            resp: HttpResponse = self._http.get_json(self.CONFIG_PATH, headers=headers)
        except HttpClientError as e:
            if e.status_code == 304:
                # 304 is treated as 200 by urlopen, but if it arrives as error:
                return RuntimeConfigSnapshot(
                    status="not_modified",
                    etag=etag,
                    config_hash=etag,
                    fetched_at=now,
                    not_modified=True,
                )
            if self._log:
                self._log.log(
                    level="error",
                    event="runtime_config_fetch_failed",
                    message=f"Config fetch failed: {e}",
                )
            raise

        # URLlib treats 304 as an error (HTTPError), so we only get here for 2xx.
        # But just in case:
        if resp.status_code == 304:
            return RuntimeConfigSnapshot(
                status="not_modified",
                etag=etag,
                config_hash=etag,
                fetched_at=now,
                not_modified=True,
            )

        # ── 4. Parse 200 response ────────────────────────────────────
        body = resp.json_body

        if not isinstance(body, dict):
            raise HttpClientError(
                status_code=resp.status_code,
                message="Invalid config response: expected JSON object",
                retryable=False,
            )

        config_hash = body.get("config_hash", "")
        if not config_hash or not isinstance(config_hash, str):
            raise HttpClientError(
                status_code=resp.status_code,
                message="Invalid config response: missing or invalid config_hash",
                retryable=False,
            )

        config = body.get("config")
        if config is None:
            raise HttpClientError(
                status_code=resp.status_code,
                message="Invalid config response: missing 'config' field",
                retryable=False,
            )

        # ── 5. Security: validate no forbidden keys/values ───────────
        try:
            _validate_config_safe(config)
        except ValueError as e:
            raise HttpClientError(
                status_code=resp.status_code,
                message=str(e),
                retryable=False,
            ) from None

        # ── 6. Extract ETag from response headers ────────────────────
        # SafeHttpClient doesn't expose raw response headers, but we can
        # use config_hash as the ETag (backend returns ETag = config_hash)
        response_etag = body.get("etag") or config_hash

        generated_at = body.get("generated_at")
        if generated_at and not isinstance(generated_at, str):
            generated_at = None

        snapshot = RuntimeConfigSnapshot(
            status="updated",
            config_hash=config_hash,
            etag=response_etag,
            generated_at=generated_at,
            config=config,
            fetched_at=now,
            not_modified=False,
        )

        if self._log:
            self._log.log(
                level="info",
                event="runtime_config_fetched",
                message="Runtime config fetched successfully",
                extra=snapshot.safe_summary(),
            )

        return snapshot
