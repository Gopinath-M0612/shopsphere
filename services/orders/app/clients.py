"""HTTP clients for the catalog and inventory services.

Every call has a timeout and a bounded number of retries with backoff.
Only network errors and 5xx answers are retried; 4xx answers are final.
"""
import logging
import time
from typing import Any, Optional

import httpx

from .config import settings
from .logging_setup import log_fields, request_id_var
from .metrics import UPSTREAM_CALLS

log = logging.getLogger("orders.clients")

_http = httpx.Client(timeout=settings.http_timeout_seconds)


class UpstreamError(Exception):
    """The other service is down, slow, or broken (callers should answer 503)."""

    def __init__(self, target: str, message: str):
        super().__init__(f"{target}: {message}")
        self.target = target


class UpstreamRejected(Exception):
    """The other service answered with a 4xx (callers decide what it means)."""

    def __init__(self, target: str, status: int, body: Any):
        super().__init__(f"{target} answered {status}")
        self.target = target
        self.status = status
        self.body = body


def _call(target: str, method: str, url: str, json: Optional[dict] = None) -> Any:
    headers = {"x-request-id": request_id_var.get()}
    attempts = settings.http_retries + 1
    last_error = "unknown"
    for attempt in range(1, attempts + 1):
        try:
            resp = _http.request(method, url, json=json, headers=headers)
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            UPSTREAM_CALLS.labels(target, "network_error").inc()
            log.warning("upstream call failed", extra=log_fields(
                target=target, url=url, attempt=attempt, attempts=attempts, error=last_error))
        else:
            if resp.status_code < 400:
                UPSTREAM_CALLS.labels(target, "ok").inc()
                return resp.json()
            if resp.status_code < 500:
                UPSTREAM_CALLS.labels(target, "rejected").inc()
                try:
                    body = resp.json()
                except ValueError:
                    body = resp.text
                raise UpstreamRejected(target, resp.status_code, body)
            last_error = f"HTTP {resp.status_code}"
            UPSTREAM_CALLS.labels(target, "server_error").inc()
            log.warning("upstream returned server error", extra=log_fields(
                target=target, url=url, status=resp.status_code, attempt=attempt, attempts=attempts))
        if attempt < attempts:
            time.sleep(0.2 * (2 ** (attempt - 1)))
    raise UpstreamError(target, last_error)


def get_product(sku: str) -> dict:
    return _call("catalog", "GET", f"{settings.catalog_url}/products/by-sku/{sku}")


def reserve(order_id: str, items: list) -> dict:
    # safe to retry: inventory treats a repeated order_id as a replay
    return _call("inventory", "POST", f"{settings.inventory_url}/reservations",
                 json={"order_id": order_id, "items": items})


def release(order_id: str) -> Optional[dict]:
    try:
        return _call("inventory", "DELETE", f"{settings.inventory_url}/reservations/{order_id}")
    except UpstreamRejected as exc:
        if exc.status == 404:
            return None
        raise


def health(url: str) -> bool:
    try:
        return _http.get(f"{url}/health", timeout=1.0).status_code == 200
    except httpx.HTTPError:
        return False


def close() -> None:
    _http.close()
    time.sleep(0)
