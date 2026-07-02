"""
Retail Media Platform — Mock Adapter Worker.

Phase 1: Minimal adapter skeleton. No NATS, no real channel logic.
Health-check only via embedded HTTP server.

Purpose: Provide a working adapter stub for Phase 1 infrastructure testing.
In later phases, this becomes a template for real channel adapters (KSO, Android, etc.).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from packages.observability import setup_logging

SERVICE_NAME = "adapter-mock"
logger = setup_logging(SERVICE_NAME)


async def health_http_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json as json_mod
    import threading

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/health/live", "/health/ready"):
                body = json_mod.dumps({
                    "status": "ok",
                    "service": SERVICE_NAME,
                    "channel": "mock",
                    "checks": {
                        "nats": "not_configured",
                    },
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args):
            pass

    port = int(os.environ.get("MOCK_ADAPTER_PORT", "8100"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health HTTP server on port %s", port)
    return server


async def main():
    logger.info("Starting %s (phase 1 skeleton, channel=mock)", SERVICE_NAME)
    server = await health_http_server()
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
