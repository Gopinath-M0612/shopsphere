"""What the worker does for each event type.

order.created   -> "payment check" -> CONFIRMED -> commit stock -> wait -> SHIPPED, with emails
order.cancelled -> cancellation email
other types     -> acknowledged and ignored

Every step is idempotent so a retried event never double-ships an order.
"""
import logging
import random
import time

import httpx

from . import logs
from .config import settings
from .metrics import EMAILS

log = logging.getLogger("worker.handlers")


class RetryableError(Exception):
    """Temporary problem (network, 5xx). The event will be redelivered."""


class PermanentError(Exception):
    """The event can never succeed (bad data, 4xx). It goes to the dead-letter stream."""


_http = httpx.Client(timeout=settings.http_timeout_seconds)


def _request(method: str, url: str, **kwargs) -> dict:
    headers = kwargs.pop("headers", {})
    headers["x-internal-token"] = settings.internal_api_token
    try:
        resp = _http.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        raise RetryableError(f"{method} {url}: {type(exc).__name__}: {exc}") from exc
    if resp.status_code >= 500:
        raise RetryableError(f"{method} {url}: HTTP {resp.status_code}")
    if resp.status_code >= 400:
        raise PermanentError(f"{method} {url}: HTTP {resp.status_code} {resp.text[:200]}")
    return resp.json()


def send_email(template: str, to: str, **context) -> None:
    """Stand-in for a real email provider: we just log the message."""
    EMAILS.labels(template).inc()
    log.info("email sent", extra=logs.fields(template=template, to=to, **context))


def set_status(order_id: str, status: str, reason: str = None) -> dict:
    return _request("PATCH", f"{settings.orders_url}/internal/orders/{order_id}/status",
                    json={"status": status, "reason": reason})


def payment_approved(data: dict) -> bool:
    """Fake payment provider: emails starting with 'declined' are declined."""
    return not data["customer_email"].lower().startswith("declined")


def handle_order_created(data: dict) -> None:
    order_id = data["order_id"]
    order = _request("GET", f"{settings.orders_url}/orders/{order_id}")
    if order["status"] in ("SHIPPED", "CANCELLED"):
        log.info("order already final, skipping", extra=logs.fields(order_id=order_id, status=order["status"]))
        return

    if order["status"] == "PENDING":
        if not payment_approved(data):
            log.warning("payment declined, cancelling order", extra=logs.fields(order_id=order_id))
            _request("POST", f"{settings.orders_url}/orders/{order_id}/cancel",
                     json={"reason": "payment declined"})
            return
        set_status(order_id, "CONFIRMED")
        send_email("order_confirmed", data["customer_email"], order_id=order_id, total=data.get("total"))

    _request("POST", f"{settings.inventory_url}/reservations/{order_id}/commit")
    time.sleep(settings.ship_delay_seconds)  # packing the parcel...
    set_status(order_id, "SHIPPED")
    send_email("order_shipped", data["customer_email"], order_id=order_id)


def handle_order_cancelled(data: dict) -> None:
    send_email("order_cancelled", data["customer_email"], order_id=data["order_id"], reason=data.get("reason"))


HANDLERS = {
    "order.created": handle_order_created,
    "order.cancelled": handle_order_cancelled,
}


def dispatch(event_type: str, data: dict) -> bool:
    """Returns True if handled, False if the type is not ours."""
    if settings.chaos_error_rate > 0 and random.random() < settings.chaos_error_rate:
        raise RetryableError("chaos: injected failure")
    handler = HANDLERS.get(event_type)
    if handler is None:
        return False
    try:
        handler(data)
    except KeyError as exc:
        raise PermanentError(f"event is missing field {exc}") from exc
    return True


def close() -> None:
    _http.close()
