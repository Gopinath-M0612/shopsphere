"""Integration tests. Needs a real PostgreSQL in DATABASE_URL (CI starts one as a service).

Example:
    DATABASE_URL=postgresql://catalog:catalog@localhost:5432/catalog_test python -m pytest -q
"""
import uuid

from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def test_health():
    with client() as c:
        body = c.get("/health").json()
        assert body["status"] == "ok"
        assert body["service"] == "catalog"


def test_ready_reports_database():
    with client() as c:
        r = c.get("/ready")
        assert r.status_code == 200
        assert r.json()["checks"]["database"] == "ok"


def test_seeded_products_are_listed():
    with client() as c:
        page = c.get("/products?page_size=50").json()
        assert page["total"] >= 12
        assert any(p["sku"] == "EL-1001" for p in page["items"])


def test_lookup_by_sku():
    with client() as c:
        r = c.get("/products/by-sku/BK-3001")
        assert r.status_code == 200
        assert r.json()["category"] == "books"


def test_unknown_sku_is_404():
    with client() as c:
        assert c.get("/products/by-sku/NOPE-0000").status_code == 404


def test_create_and_update_product():
    sku = "TS-" + uuid.uuid4().hex[:6].upper()
    with client() as c:
        r = c.post("/products", json={"sku": sku, "name": "Test item", "price": "10.50",
                                       "category_slug": "home"})
        assert r.status_code == 201
        pid = r.json()["id"]
        r = c.patch(f"/products/{pid}", json={"price": "12.00"})
        assert r.status_code == 200
        assert r.json()["price"] == 12.0


def test_validation_rejects_bad_price():
    with client() as c:
        r = c.post("/products", json={"sku": "BAD-1", "name": "x" * 3, "price": "-5",
                                       "category_slug": "home"})
        assert r.status_code == 422


def test_metrics_exposed():
    with client() as c:
        c.get("/health")
        text = c.get("/metrics").text
        assert "http_requests_total" in text
