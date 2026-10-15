"""Internal endpoints, only for other ShopSphere services (the worker).

Protected by a shared token in the X-Internal-Token header. The gateway must
never route /internal/* from the internet.
"""
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from .. import db, outbox, repository
from ..config import settings
from ..logging_setup import log_fields
from ..metrics import STATUS_CHANGES
from ..models import OrderOut, StatusChange

log = logging.getLogger("orders.internal")


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_internal_token, settings.internal_api_token):
        log.warning("rejected internal call with bad token")
        raise HTTPException(401, "invalid internal token")


router = APIRouter(prefix="/internal/orders", tags=["internal"],
                   dependencies=[Depends(require_internal_token)])


@router.patch("/{order_id}/status", response_model=OrderOut)
def change_status(order_id: str, body: StatusChange):
    with db.engine.begin() as conn:
        order = repository.get_order(conn, order_id, lock=True)
        if order is None:
            raise HTTPException(404, "order not found")
        current = order["status"]
        if current == body.status:
            return order  # idempotent: the worker may retry
        if body.status not in repository.TRANSITIONS[current]:
            raise HTTPException(409, f"cannot move order from {current} to {body.status}")
        repository.set_status(conn, order_id, body.status, body.reason)
        outbox.add_event(conn, f"order.{body.status.lower()}", {
            "order_id": order_id, "customer_email": order["customer_email"],
            "from": current, "to": body.status, "reason": body.reason})
        order = repository.get_order(conn, order_id)
    outbox.notify()
    STATUS_CHANGES.labels(body.status).inc()
    log.info("order status changed", extra=log_fields(order_id=order_id, frm=current, to=body.status))
    return order
