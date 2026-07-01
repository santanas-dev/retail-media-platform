"""Request logging middleware.

Logs structured JSON per request: method, path, status_code, duration_ms,
correlation_id, user_id (if available). Never logs body, tokens, secrets.
"""

import time
import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("request_logger")
logger.setLevel(logging.INFO)

# Ensure handler (JSON to stdout)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False

FORBIDDEN_HEADERS = frozenset({
    "authorization", "cookie", "set-cookie",
    "x-api-key", "x-auth-token", "proxy-authorization",
})


def _safe_user_id(request: Request) -> str | None:
    """Extract user_id from request state if available, never from token."""
    # FastAPI auth may set request.state.user_id
    uid = getattr(request.state, "user_id", None)
    return uid if uid else None


def _safe_device_code(request: Request) -> str | None:
    """Extract device_code from request state if available."""
    dc = getattr(request.state, "device_code", None)
    return dc if dc else None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response: Response = await call_next(request)
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)

        log_entry = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": elapsed_ms,
            "correlation_id": getattr(request.state, "correlation_id", "unknown"),
        }

        user_id = _safe_user_id(request)
        if user_id:
            log_entry["user_id"] = user_id

        device_code = _safe_device_code(request)
        if device_code:
            log_entry["device_code"] = device_code

        # NEVER log: body, authorization, cookies, tokens
        logger.info(json.dumps(log_entry, ensure_ascii=False))
        return response
