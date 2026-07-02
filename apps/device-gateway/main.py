"""
Retail Media Platform — Device Gateway.

Phase 1: Minimal FastAPI skeleton. No auth, no DB, no business logic.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI
from packages.observability import setup_logging, log_request_middleware

SERVICE_NAME = "device-gateway"
logger = setup_logging(SERVICE_NAME)

app = FastAPI(
    title="RMP Device Gateway",
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
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "checks": {
            "redis": "not_configured",
            "event_bus": "not_configured",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DEVICE_GATEWAY_PORT", "8001"))
    logger.info("Starting %s on port %s", SERVICE_NAME, port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
