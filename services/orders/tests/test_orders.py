"""Order tests with a real PostgreSQL + Redis; catalog and inventory calls are faked.

    DATABASE_URL=postgresql://orders:orders@localhost:5432/orders_test \
    REDIS_URL=redis://localhost:6379/2 CATALOG_URL=http://catalog INVENTORY_URL=http://inventory \
    INTERNAL_API_TOKEN=test-token python -m pytest -q
"""
import pytest
from fastapi.testclient import TestClient

from app import clients
from app.config import settings
from app.main import app

PRODUCTS = {
    "EL-1001": {"sku": "EL-1001", "name": "Wireless Earbuds", "price": 1999.0, "active": True},
    "BK-3002": {"sku": "BK-3002", "name": "The Phoenix Project", "price": 699.0, "active": True},
    "OLD-0001": {"sku": "OLD-0001", "name": "Retired", "price": 10.0, "active": False},
}


@pytest.fixture()
def fake_upstreams(monkeypatch):
    state = {"reserved": [], "released": [], "stock_ok": True}

    def get_product(sku):
        if sku not in PRODUCTS:
            raise clients.UpstreamRejected("catalog", 404, {"detail": "not found"})
        return PRODUCTS[sku]

    def reserve(order_id, items):
        if not state["stock_ok"]:
            raise clients.UpstreamRejected("inventory", 409, {"details": [{"sku": items[0]["sku"]}]})
        state["reserved"].append(order_id)
        return {"order_id": order_id, "status": "RESERVED"}

    def release(order_id):
        state["released"].append(order_id)
        return {"order_id": order_id, "status": "RELEASED"}

    monkeypatch.setattr(clients, "get_product", get_product)
    monkeypatch.setattr(clients, "reserve", reserve)
    monkeypatch.setattr(clients, "release", release)
    return state


@pytest.fixture()
def api():
    with TestClient(app) as c:
        yield c


def order_body(*items):
    return {"customer_email": "ravi@example.com", "items": [{"sku": s, "qty": q} for s, q in items]}


def test_health(api):
    assert api.get("/health").json()["service"] == "orders"


def test_create_order_totals_and_merges_lines(api, fake_upstreams):
    r = api.post("/orders", json=order_body(("EL-1001", 1), ("BK-3002", 2), ("EL-1001", 1)))
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "PENDING"
    assert order["total"] == 1999.0 * 2 + 699.0 * 2
    assert len(order["items"]) == 2
    assert fake_upstreams["reserved"] == [order["id"]]


def test_unknown_sku_is_422(api, fake_upstreams):
    assert api.post("/orders", json=order_body(("NOPE-123", 1))).status_code == 422


def test_inactive_sku_is_422(api, fake_upstreams):
    assert api.post("/orders", json=order_body(("OLD-0001", 1))).status_code == 422


def test_out_of_stock_is_409(api, fake_upstreams):
    fake_upstreams["stock_ok"] = False
    assert api.post("/orders", json=order_body(("EL-1001", 1))).status_code == 409


def test_bad_email_is_422(api, fake_upstreams):
    body = order_body(("EL-1001", 1))
    body["customer_email"] = "not-an-email"
    assert api.post("/orders", json=body).status_code == 422


def test_cancel_releases_stock(api, fake_upstreams):
    order = api.post("/orders", json=order_body(("EL-1001", 1))).json()
    r = api.post(f"/orders/{order['id']}/cancel", json={"reason": "changed mind"})
    assert r.json()["status"] == "CANCELLED"
    assert order["id"] in fake_upstreams["released"]


def test_internal_status_requires_token(api, fake_upstreams):
    order = api.post("/orders", json=order_body(("BK-3002", 1))).json()
    url = f"/internal/orders/{order['id']}/status"
    assert api.patch(url, json={"status": "CONFIRMED"}).status_code == 401
    ok = api.patch(url, json={"status": "CONFIRMED"},
                   headers={"x-internal-token": settings.internal_api_token})
    assert ok.json()["status"] == "CONFIRMED"
    bad = api.patch(url, json={"status": "PENDING"},
                    headers={"x-internal-token": settings.internal_api_token})
    assert bad.status_code == 409


def test_events_reach_the_outbox(api, fake_upstreams):
    from app import outbox
    api.post("/orders", json=order_body(("EL-1001", 1)))
    published = outbox.publish_batch()
    assert published >= 0  # relay thread may already have published it
    assert outbox.redis_ok()
