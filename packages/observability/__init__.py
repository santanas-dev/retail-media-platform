"""
Retail Media Platform — Observability Helpers.

Phase 1: Structured JSON logging and correlation ID propagation.
No external dependencies beyond stdlib.
"""

import json
import logging
import os
import sys
import time
import uuid
from typing import Optional


# ---------------------------------------------------------------------------
# Correlation ID
# ---------------------------------------------------------------------------

def new_correlation_id() -> str:
    """Generate a new correlation ID (UUIDv4)."""
    return str(uuid.uuid4())


def get_correlation_id(
    headers: dict,
    header_name: str = "X-Correlation-ID",
) -> str:
    """Extract correlation ID from HTTP headers, or generate a new one."""
    cid = headers.get(header_name)
    if cid:
        return str(cid)
    return new_correlation_id()


# ---------------------------------------------------------------------------
# Structured JSON Logger
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """Emit log records as JSON to stdout."""

    SANITIZED_FIELDS = frozenset({
        "password", "token", "secret", "api_key", "access_key",
        "authorization", "cookie", "signature",
    })

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "service": getattr(record, "service", os.environ.get("RMP_SERVICE", "unknown")),
            "correlation_id": getattr(record, "correlation_id", None),
            "message": record.getMessage(),
        }

        # Optional fields
        for attr in ("user_id", "device_id", "action", "duration_ms"):
            if hasattr(record, attr):
                entry[attr] = getattr(record, attr)

        if record.exc_info and record.exc_info[1]:
            entry["error"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(entry, default=str)


def setup_logging(
    service_name: str,
    level: int = logging.INFO,
) -> logging.Logger:
    """Configure structured JSON logging for a service."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger(service_name)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False

    # Allow injection of service name via LogRecord extra
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "service") or record.service is None:
            record.service = service_name
        return record

    logging.setLogRecordFactory(record_factory)

    return logger


# ---------------------------------------------------------------------------
# HTTP Logging Middleware (FastAPI-compatible)
# ---------------------------------------------------------------------------

async def log_request_middleware(request, call_next):
    """ASGI middleware: log every request with correlation ID, duration, and status."""
    cid = get_correlation_id(dict(request.headers))
    request.state.correlation_id = cid
    request.state.service = os.environ.get("RMP_SERVICE", "unknown")

    start = time.monotonic()
    response = await call_next(request)
    duration_ms = int((time.monotonic() - start) * 1000)

    logger = logging.getLogger(request.state.service)
    logger.info(
        "%s %s → %s (%dms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        extra={
            "correlation_id": cid,
            "duration_ms": duration_ms,
            "action": f"http.{request.method}.{request.url.path}",
        },
    )
    response.headers["X-Correlation-ID"] = cid
    return response
