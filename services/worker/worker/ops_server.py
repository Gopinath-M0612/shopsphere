"""Tiny HTTP server for /health, /ready and /metrics (the worker has no API).

Runs in a background thread on OPS_PORT so Kubernetes probes and Prometheus
can reach the worker.
"""
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .config import settings
from .metrics import LAST_SUCCESS

log = logging.getLogger("worker.ops")


def make_handler(consumer):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str = "application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 (name required by BaseHTTPRequestHandler)
            if self.path == "/health":
                body = {"status": "ok", "service": settings.service_name, "version": settings.version}
                self._send(200, json.dumps(body).encode())
            elif self.path == "/ready":
                redis_ok = consumer.ping()
                last = LAST_SUCCESS._value.get()  # noqa: SLF001
                body = {
                    "status": "ready" if redis_ok else "not-ready",
                    "checks": {"redis": "ok" if redis_ok else "fail"},
                    "last_success_seconds_ago": round(time.time() - last, 1) if last else None,
                }
                self._send(200 if redis_ok else 503, json.dumps(body).encode())
            elif self.path == "/metrics":
                self._send(200, generate_latest(), CONTENT_TYPE_LATEST)
            else:
                self._send(404, b'{"detail":"not found"}')

        def log_message(self, *_args):  # silence default stderr access log
            return

    return Handler


def start(consumer) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", settings.ops_port), make_handler(consumer))
    threading.Thread(target=server.serve_forever, name="ops-server", daemon=True).start()
    log.info("ops server listening", extra={"fields": {"port": settings.ops_port}})
    return server
