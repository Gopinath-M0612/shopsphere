"""Request ID, access log, metrics and chaos (fault injection) middleware."""
import asyncio
import logging
import random
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .logging_setup import log_fields, request_id_var
from .metrics import IN_FLIGHT, LATENCY, REQUESTS

log = logging.getLogger("orders.http")

QUIET_PATHS = {"/health", "/ready", "/metrics"}


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        IN_FLIGHT.labels(settings.service_name).inc()
        start = time.perf_counter()
        status = 500
        try:
            if request.url.path not in QUIET_PATHS:
                if settings.chaos_latency_ms > 0:
                    await asyncio.sleep(settings.chaos_latency_ms / 1000)
                if settings.chaos_error_rate > 0 and random.random() < settings.chaos_error_rate:
                    log.error("chaos: injected failure")
                    response = JSONResponse({"detail": "injected failure (chaos)"}, status_code=500)
                    status = 500
                    response.headers["x-request-id"] = request_id
                    return response

            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        except Exception:
            log.exception("unhandled error")
            return JSONResponse({"detail": "internal error", "request_id": request_id}, status_code=500)
        finally:
            elapsed = time.perf_counter() - start
            route = _route_template(request)
            REQUESTS.labels(settings.service_name, request.method, route, str(status)).inc()
            LATENCY.labels(settings.service_name, request.method, route).observe(elapsed)
            IN_FLIGHT.labels(settings.service_name).dec()
            if request.url.path not in QUIET_PATHS:
                log.info("request", extra=log_fields(
                    method=request.method, path=request.url.path, status=status,
                    duration_ms=round(elapsed * 1000, 1),
                    client=request.client.host if request.client else None))
            request_id_var.reset(token)
