"""
Retail Media Platform — Control API.

Phase 1: Minimal FastAPI skeleton. No auth, no DB, no business logic.
"""

import os
import sys

# Ensure shared packages are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import logging
from packages.observability import setup_logging, log_request_middleware

SERVICE_NAME = "control-api"
logger = setup_logging(SERVICE_NAME)

app = FastAPI(
    title="RMP Control API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)
app.middleware("http")(log_request_middleware)


@app.get("/health/live")
async def health_live():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/health/ready")
async def health_ready():
    """Phase 1: always ready. Later: check DB, Redis, upstream deps."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "checks": {
            "database": "not_configured",
            "redis": "not_configured",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("CONTROL_API_PORT", "8000"))
    logger.info("Starting %s on port %s", SERVICE_NAME, port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
