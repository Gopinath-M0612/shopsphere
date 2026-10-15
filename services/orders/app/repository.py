"""SQL for orders, kept in one place."""
from typing import Optional

from sqlalchemy import text

# which status may follow which
TRANSITIONS = {
    "PENDING": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"SHIPPED", "CANCELLED"},
    "SHIPPED": set(),
    "CANCELLED": set(),
}

ORDER_COLUMNS = (
    "id, customer_email, status, total::float AS total, currency, cancel_reason, "
    "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') AS created_at, "
    "to_char(updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') AS updated_at"
)


def insert_order(conn, order_id: str, email: str, total, currency: str, lines: list) -> None:
    conn.execute(text(
        "INSERT INTO orders(id, customer_email, status, total, currency) "
        "VALUES (:id, :email, 'PENDING', :total, :currency)"),
        {"id": order_id, "email": email, "total": total, "currency": currency})
    for line in lines:
        conn.execute(text(
            "INSERT INTO order_items(order_id, sku, name, unit_price, qty) "
            "VALUES (:order_id, :sku, :name, :unit_price, :qty)"),
            {"order_id": order_id, **line})


def get_order(conn, order_id: str, lock: bool = False) -> Optional[dict]:
    row = conn.execute(
        text(f"SELECT {ORDER_COLUMNS} FROM orders WHERE id = :id" + (" FOR UPDATE" if lock else "")),
        {"id": order_id}).mappings().first()
    if row is None:
        return None
    order = dict(row)
    items = conn.execute(text(
        "SELECT sku, name, unit_price::float AS unit_price, qty, "
        "(unit_price * qty)::float AS line_total FROM order_items WHERE order_id = :id ORDER BY sku"),
        {"id": order_id}).mappings().all()
    order["items"] = [dict(i) for i in items]
    return order


def list_orders(conn, email: Optional[str], status: Optional[str], limit: int, offset: int) -> list:
    where, params = [], {"limit": limit, "offset": offset}
    if email:
        where.append("customer_email = :email")
        params["email"] = email
    if status:
        where.append("status = :status")
        params["status"] = status
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(text(
        f"SELECT {ORDER_COLUMNS} FROM orders {clause} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
        params).mappings().all()
    return [dict(r) for r in rows]


def set_status(conn, order_id: str, status: str, reason: Optional[str] = None) -> None:
    conn.execute(text(
        "UPDATE orders SET status = :status, cancel_reason = COALESCE(:reason, cancel_reason), "
        "updated_at = now() WHERE id = :id"),
        {"id": order_id, "status": status, "reason": reason})


def status_counts(conn) -> dict:
    rows = conn.execute(text("SELECT status, count(*) FROM orders GROUP BY status")).all()
    return {status: count for status, count in rows}
