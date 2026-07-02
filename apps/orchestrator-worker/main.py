"""
Retail Media Platform — Orchestrator Worker.

Phase 1: Minimal async worker skeleton. No NATS, no DB yet.
Health-check only via embedded HTTP server.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from packages.observability import setup_logging

SERVICE_NAME = "orchestrator-worker"
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
                    "checks": {
                        "database": "not_configured",
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

    port = int(os.environ.get("ORCHESTRATOR_PORT", "8003"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health HTTP server on port %s", port)
    return server


async def main():
    logger.info("Starting %s (phase 1 skeleton)", SERVICE_NAME)
    server = await health_http_server()
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
