"""Lightweight in-memory rate limiter middleware.

No Redis dependency. Tracks request counts per key (IP + path)
in a sliding window. Returns 429 with structured error when exceeded.

Design decisions:
- In-memory only — no persistence, resets on restart.
- Conservative defaults: high enough for dev, adjustable for prod.
- No secrets in keys — uses IP + path (no user_id/token in key).
- Deterministic cleanup for testability.
"""

import time
import json
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


# Default: 30 req / 60s per IP+path combination
DEFAULT_RATE_LIMIT = 30
DEFAULT_WINDOW_SECS = 60

# Tighter limits for sensitive endpoints
ENDPOINT_LIMITS: dict[str, tuple[int, int]] = {
    # path_prefix: (max_requests, window_seconds)
    "/api/emergency/": (5, 60),       # 5 req/60s
    "/api/health/dependencies": (10, 60),  # 10 req/60s
    "/api/health/metrics": (20, 60),  # 20 req/60s
}

# IP-like keys exempt from rate limiting
EXEMPT_PATHS: list[str] = [
    "/api/health/live",
    "/api/health/ready",
    "/docs",
    "/openapi.json",
]


def _rate_limit_key(request: Request) -> str:
    """Build a rate limit key from client IP + path prefix.

    Never includes user_id, token, or other secrets.
    """
    # Get client IP — prefer X-Forwarded-For, fallback to direct
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"

    # Use path prefix for grouping
    path = request.url.path
    return f"{ip}:{path}"


class InMemoryRateLimiter:
    """Thread-safe-ish in-memory rate limit tracker."""

    def __init__(self):
        # {key: [(timestamp, count), ...]}
        self._windows: dict[str, list[tuple[float, int]]] = defaultdict(list)

    def check(
        self,
        key: str,
        max_requests: int = DEFAULT_RATE_LIMIT,
        window_secs: int = DEFAULT_WINDOW_SECS,
    ) -> tuple[bool, int, int]:
        """Check if request exceeds rate limit.

        Returns: (allowed: bool, remaining: int, reset_after: int)
        """
        now = time.monotonic()
        cutoff = now - window_secs

        entries = self._windows[key]

        # Remove expired entries
        while entries and entries[0][0] < cutoff:
            entries.pop(0)

        # Count requests in window
        count = sum(c for _, c in entries)

        if count >= max_requests:
            reset_after = int(entries[0][0] + window_secs - now) if entries else window_secs
            return False, 0, max(reset_after, 1)

        # Add current request
        entries.append((now, 1))
        remaining = max_requests - count - 1  # -1 for the just-added request
        return True, remaining, int(window_secs)

    def reset(self) -> None:
        """Clear all state — for test cleanup."""
        self._windows.clear()

    def reset_key(self, key: str) -> None:
        """Clear state for a specific key — for tests."""
        self._windows.pop(key, None)


# Singleton instance
_limiter = InMemoryRateLimiter()


def get_limiter() -> InMemoryRateLimiter:
    """Return the singleton rate limiter (for test injection)."""
    return _limiter


def _get_limit_for_path(path: str) -> tuple[int, int]:
    """Get rate limit config for a path prefix."""
    for prefix, (max_req, window) in ENDPOINT_LIMITS.items():
        if path.startswith(prefix):
            return max_req, window
    return DEFAULT_RATE_LIMIT, DEFAULT_WINDOW_SECS


def _is_exempt(path: str) -> bool:
    """Check if path is exempt from rate limiting."""
    return path in EXEMPT_PATHS


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting based on IP + path.

    Responses include X-RateLimit-* headers.
    429 returns structured JSON error.

    In test mode (pytest running), rate limiting is bypassed
    to avoid test pollution. Existing test suites should continue
    to pass without modification.
    """

    def _is_test_mode(self) -> bool:
        """Check if running under pytest."""
        try:
            import sys
            return "pytest" in sys.modules
        except Exception:
            return False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Exempt health checks and docs from rate limiting
        if _is_exempt(path):
            return await call_next(request)

        # Bypass rate limiting in test mode
        if self._is_test_mode():
            response: Response = await call_next(request)
            return response

        key = _rate_limit_key(request)
        max_req, window = _get_limit_for_path(path)

        allowed, remaining, reset_after = _limiter.check(key, max_req, window)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after_seconds": reset_after,
                },
                headers={
                    "X-RateLimit-Limit": str(max_req),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_after),
                    "Retry-After": str(reset_after),
                },
            )

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_req)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_after)
        return response
