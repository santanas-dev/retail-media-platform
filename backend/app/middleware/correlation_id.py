"""Correlation ID middleware.

Adds X-Correlation-ID to every request/response.
Reads from X-Request-ID or X-Correlation-ID header (prefer latter).
Generates UUID if absent. Sanitizes length.
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

MAX_CORRELATION_ID_LENGTH = 128
HEADER_CORRELATION_ID = "X-Correlation-ID"
HEADER_REQUEST_ID = "X-Request-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        raw = request.headers.get(
            HEADER_CORRELATION_ID,
            request.headers.get(HEADER_REQUEST_ID, ""),
        ).strip()

        if raw and len(raw) <= MAX_CORRELATION_ID_LENGTH:
            clean = raw.replace("\n", "").replace("\r", "").replace("\0", "")
            cid = clean[:MAX_CORRELATION_ID_LENGTH]
        else:
            cid = str(uuid.uuid4())

        request.state.correlation_id = cid

        response: Response = await call_next(request)
        response.headers[HEADER_CORRELATION_ID] = cid
        return response
