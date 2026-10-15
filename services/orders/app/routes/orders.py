"""Public order endpoints: create, read, list, cancel."""
import logging
import uuid
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from .. import clients, db, outbox, repository
from ..config import settings
from ..logging_setup import log_fields
from ..metrics import ORDER_VALUE, ORDERS_CREATED, ORDERS_REJECTED, STATUS_CHANGES
from ..models import CancelIn, OrderIn, OrderOut, OrderStatus

router = APIRouter(prefix="/orders", tags=["orders"])
log = logging.getLogger("orders.api")


def _merge_items(body: OrderIn) -> list:
    merged = {}
    for item in body.items:
        merged[item.sku] = merged.get(item.sku, 0) + item.qty
    return [{"sku": sku, "qty": qty} for sku, qty in sorted(merged.items())]


def _price_lines(items: list) -> list:
    """Ask the catalog for the current name and price of every SKU."""
    lines = []
    for item in items:
        try:
            product = clients.get_product(item["sku"])
        except clients.UpstreamRejected as exc:
            if exc.status == 404:
                ORDERS_REJECTED.labels("unknown_sku").inc()
                raise HTTPException(422, f"unknown product {item['sku']}")
            raise HTTPException(502, f"catalog rejected lookup for {item['sku']}")
        except clients.UpstreamError:
            ORDERS_REJECTED.labels("catalog_unavailable").inc()
            raise HTTPException(503, "catalog service unavailable, try again shortly")
        if not product.get("active", False):
            ORDERS_REJECTED.labels("inactive_sku").inc()
            raise HTTPException(422, f"product {item['sku']} is not for sale")
        lines.append({"sku": item["sku"], "name": product["name"],
                      "unit_price": Decimal(str(product["price"])), "qty": item["qty"]})
    return lines


@router.post("", response_model=OrderOut, status_code=201)
def create_order(body: OrderIn):
    items = _merge_items(body)
    lines = _price_lines(items)
    total = sum((line["unit_price"] * line["qty"] for line in lines), Decimal("0"))
    order_id = "ord_" + uuid.uuid4().hex[:20]

    # 1) hold the stock
    try:
        clients.reserve(order_id, items)
    except clients.UpstreamRejected as exc:
        if exc.status == 409:
            ORDERS_REJECTED.labels("out_of_stock").inc()
            details = exc.body.get("details") if isinstance(exc.body, dict) else None
            raise HTTPException(409, {"message": "some items are out of stock", "items": details})
        raise HTTPException(502, f"inventory rejected the reservation ({exc.status})")
    except clients.UpstreamError:
        ORDERS_REJECTED.labels("inventory_unavailable").inc()
        raise HTTPException(503, "inventory service unavailable, try again shortly")

    # 2) save order + event atomically; if that fails, give the stock back
    try:
        with db.engine.begin() as conn:
            repository.insert_order(conn, order_id, body.customer_email, total, settings.currency, lines)
            outbox.add_event(conn, "order.created", {
                "order_id": order_id, "customer_email": body.customer_email,
                "total": str(total), "currency": settings.currency, "items": items,
            })
            order = repository.get_order(conn, order_id)
    except Exception:
        log.exception("saving order failed, releasing reservation", extra=log_fields(order_id=order_id))
        try:
            clients.release(order_id)
        except Exception:  # noqa: BLE001
            log.error("COMPENSATION FAILED: reservation left behind", extra=log_fields(order_id=order_id))
        raise HTTPException(500, "could not save order")

    outbox.notify()
    ORDERS_CREATED.inc()
    ORDER_VALUE.observe(float(total))
    log.info("order created", extra=log_fields(order_id=order_id, total=str(total), items=len(items)))
    return order


@router.get("", response_model=List[OrderOut])
def list_orders(
    email: Optional[str] = None,
    status: Optional[OrderStatus] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    with db.engine.connect() as conn:
        return repository.list_orders(conn, email, status, limit, offset)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: str):
    with db.engine.connect() as conn:
        order = repository.get_order(conn, order_id)
    if order is None:
        raise HTTPException(404, "order not found")
    return order


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: str, body: Optional[CancelIn] = None):
    reason = (body or CancelIn()).reason
    with db.engine.begin() as conn:
        order = repository.get_order(conn, order_id, lock=True)
        if order is None:
            raise HTTPException(404, "order not found")
        if order["status"] == "CANCELLED":
            return order
        if "CANCELLED" not in repository.TRANSITIONS[order["status"]]:
            raise HTTPException(409, f"order is {order['status']} and can no longer be cancelled")
        try:
            clients.release(order_id)
        except clients.UpstreamError:
            raise HTTPException(503, "inventory service unavailable, try again shortly")
        except clients.UpstreamRejected as exc:
            raise HTTPException(409, f"inventory refused to release stock ({exc.status})")
        repository.set_status(conn, order_id, "CANCELLED", reason)
        outbox.add_event(conn, "order.cancelled", {
            "order_id": order_id, "customer_email": order["customer_email"], "reason": reason})
        order = repository.get_order(conn, order_id)
    outbox.notify()
    STATUS_CHANGES.labels("CANCELLED").inc()
    log.info("order cancelled", extra=log_fields(order_id=order_id, reason=reason))
    return order
