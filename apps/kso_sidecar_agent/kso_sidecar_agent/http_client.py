"""Safe HTTP client for KSO Sidecar Agent.

Stdlib-only (no third-party dependencies).
Never logs request/response bodies, Authorization headers, or secrets.
"""

import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


# ── Forbidden substrings ──────────────────────────────────────────────

FORBIDDEN_HEADER_VALUES = [
    "token", "jwt", "password", "secret", "api_key",
    "private_key", "payment_card", "receipt",
    "local_path", "file_path",
]

FORBIDDEN_PATH_SUBSTRINGS = FORBIDDEN_HEADER_VALUES  # same list


# ══════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════

@dataclass
class HttpClientConfig:
    """Safe HTTP client configuration."""

    base_url: str           # e.g. "https://retail-media.example.local/api/device-gateway"
    timeout_sec: int = 10   # 1–120
    tls_verify: bool = True

    def __post_init__(self) -> None:
        # Validate base_url
        if not self.base_url or not isinstance(self.base_url, str):
            raise ValueError("base_url is required")

        parsed = urlparse(self.base_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"base_url must be http:// or https://, got '{parsed.scheme}'"
            )
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain username/password")
        if parsed.query:
            raise ValueError("base_url must not contain query string")

        # Validate timeout
        if not isinstance(self.timeout_sec, (int, float)) or self.timeout_sec < 1 or self.timeout_sec > 120:
            raise ValueError(f"timeout_sec must be 1-120, got {self.timeout_sec}")

        # Ensure base_url ends with / for proper urljoin
        if not self.base_url.endswith("/"):
            self.base_url += "/"


# ══════════════════════════════════════════════════════════════════════
# Response + Error
# ══════════════════════════════════════════════════════════════════════

@dataclass
class HttpResponse:
    """Successful HTTP response."""
    status_code: int
    json_body: Any
    elapsed_ms: float

    def safe_summary(self) -> dict:
        """Return metadata only — no body, no headers."""
        return {
            "status_code": self.status_code,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


class HttpClientError(Exception):
    """Safe HTTP error — no stacktrace in user output, no body dump."""

    def __init__(
        self,
        status_code: int = 0,
        message: str = "",
        retryable: bool = False,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.retryable = retryable
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


# ══════════════════════════════════════════════════════════════════════
# Validation helpers
# ══════════════════════════════════════════════════════════════════════

# ── Allowed path exceptions ───────────────────────────────────────────

# Exact allowlist: these paths bypass the forbidden-substring check.
# Every entry is a known backend endpoint from device-gateway router.
EXACT_ALLOWED_PATHS: frozenset[str] = frozenset({
    "/api/device-gateway/auth/token",
})


def _validate_path(path: str) -> str:
    if not path or not isinstance(path, str):
        raise ValueError("path is required")
    if not path.startswith("/"):
        raise ValueError("path must start with '/'")
    if ".." in path:
        raise ValueError("path must not contain '..'")
    if "?" in path:
        raise ValueError("path must not contain query string")

    # Exact allowlist check: only these specific paths bypass forbidden check
    if path in EXACT_ALLOWED_PATHS:
        return path

    lower = path.lower()
    for forbidden in FORBIDDEN_PATH_SUBSTRINGS:
        if forbidden in lower:
            raise ValueError(
                f"path contains forbidden substring '{forbidden}'"
            )
    return path


def _validate_headers(headers: Optional[dict[str, str]]) -> dict[str, str]:
    if headers is None:
        return {}
    for key, value in headers.items():
        if not isinstance(value, str):
            raise ValueError(f"Header '{key}' value must be a string")
        lower_val = value.lower()
        for forbidden in FORBIDDEN_HEADER_VALUES:
            if forbidden in lower_val:
                raise ValueError(
                    f"Header '{key}' contains forbidden substring '{forbidden}'"
                )
    return dict(headers)


def _is_retryable(status_code: int) -> bool:
    """Return True for transient errors that should be retried."""
    if status_code == 429:
        return True
    if 500 <= status_code < 600:
        return True
    return False


# ══════════════════════════════════════════════════════════════════════
# Safe HTTP Client
# ══════════════════════════════════════════════════════════════════════

class SafeHttpClient:
    """Safe HTTP client — no body/secrets in logs, no disk storage."""

    def __init__(self, config: HttpClientConfig) -> None:
        self._config = config
        self._ssl_context: Optional[ssl.SSLContext] = None
        if not config.tls_verify:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

    def get_json(self, path: str, headers: Optional[dict[str, str]] = None) -> HttpResponse:
        """GET request, return parsed JSON."""
        return self._request("GET", path, payload=None, headers=headers)

    def post_json(self, path: str, payload: Any, headers: Optional[dict[str, str]] = None) -> HttpResponse:
        """POST request with JSON body, return parsed JSON."""
        return self._request("POST", path, payload=payload, headers=headers)

    # ── Internal ────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        headers: Optional[dict[str, str]] = None,
    ) -> HttpResponse:
        _validate_path(path)
        validated_headers = _validate_headers(headers)

        url = urljoin(self._config.base_url, path.lstrip("/"))
        body_bytes = None

        if payload is not None:
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req_headers = {
            "Accept": "application/json",
        }
        if body_bytes is not None:
            req_headers["Content-Type"] = "application/json"
        req_headers.update(validated_headers)

        req = urllib.request.Request(
            url, data=body_bytes, headers=req_headers, method=method,
        )

        start = time.monotonic()
        try:
            resp = urllib.request.urlopen(
                req, timeout=self._config.timeout_sec, context=self._ssl_context,
            )
        except urllib.error.HTTPError as e:
            elapsed = (time.monotonic() - start) * 1000
            code = e.code
            retryable = _is_retryable(code)
            raise HttpClientError(
                status_code=code,
                message=f"HTTP {code} ({elapsed:.0f}ms)",
                retryable=retryable,
            ) from None
        except urllib.error.URLError as e:
            elapsed = (time.monotonic() - start) * 1000
            reason = str(e.reason) if e.reason else "Unknown network error"
            raise HttpClientError(
                status_code=0,
                message=f"Network error: {reason} ({elapsed:.0f}ms)",
                retryable=True,
            ) from None
        except (TimeoutError, OSError) as e:
            elapsed = (time.monotonic() - start) * 1000
            raise HttpClientError(
                status_code=0,
                message=f"Connection failed: {e} ({elapsed:.0f}ms)",
                retryable=True,
            ) from None

        elapsed = (time.monotonic() - start) * 1000
        raw = resp.read()

        status_code = resp.getcode()
        if not (200 <= status_code < 300):
            retryable = _is_retryable(status_code)
            raise HttpClientError(
                status_code=status_code,
                message=f"HTTP {status_code} ({elapsed:.0f}ms)",
                retryable=retryable,
            )

        # Parse JSON
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as e:
            raise HttpClientError(
                status_code=status_code,
                message=f"Invalid JSON response ({elapsed:.0f}ms)",
                retryable=False,
            ) from None

        return HttpResponse(status_code=status_code, json_body=data, elapsed_ms=elapsed)
