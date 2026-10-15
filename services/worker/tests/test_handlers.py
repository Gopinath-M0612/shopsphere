"""Unit tests for event handling (no network needed).

    REDIS_URL=redis://localhost:6379/3 ORDERS_URL=http://orders INVENTORY_URL=http://inventory \
    INTERNAL_API_TOKEN=test SHIP_DELAY_SECONDS=0 python -m pytest -q
"""
import pytest

from worker import handlers


@pytest.fixture()
def calls(monkeypatch):
    log = []
    orders = {"ord_1": {"status": "PENDING"}}

    def fake_request(method, url, **kwargs):
        log.append((method, url.split("//", 1)[1].split("/", 1)[1], kwargs.get("json")))
        if method == "GET":
            return orders["ord_1"]
        if url.endswith("/status"):
            orders["ord_1"]["status"] = kwargs["json"]["status"]
        if url.endswith("/cancel"):
            orders["ord_1"]["status"] = "CANCELLED"
        return {}

    monkeypatch.setattr(handlers, "_request", fake_request)
    monkeypatch.setattr(handlers.time, "sleep", lambda _s: None)
    return log, orders


def created(email="ravi@example.com"):
    return {"order_id": "ord_1", "customer_email": email, "total": "999.00", "items": []}


def test_created_confirms_commits_and_ships(calls):
    log, orders = calls
    assert handlers.dispatch("order.created", created()) is True
    paths = [p for _m, p, _b in log]
    assert "internal/orders/ord_1/status" in paths
    assert "reservations/ord_1/commit" in paths
    assert orders["ord_1"]["status"] == "SHIPPED"


def test_declined_payment_cancels(calls):
    _log, orders = calls
    handlers.dispatch("order.created", created("declined@example.com"))
    assert orders["ord_1"]["status"] == "CANCELLED"


def test_already_shipped_is_skipped(calls):
    log, orders = calls
    orders["ord_1"]["status"] = "SHIPPED"
    handlers.dispatch("order.created", created())
    assert [m for m, _p, _b in log] == ["GET"]


def test_unknown_event_is_ignored(calls):
    assert handlers.dispatch("something.else", {}) is False


def test_missing_field_is_permanent(calls):
    with pytest.raises(handlers.PermanentError):
        handlers.dispatch("order.cancelled", {"order_id": "ord_1"})
