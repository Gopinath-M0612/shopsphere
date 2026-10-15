"""Prometheus metrics exposed on GET /metrics."""
from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter(
    "http_requests_total", "HTTP requests handled",
    ["service", "method", "route", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
IN_FLIGHT = Gauge("http_requests_in_flight", "Requests being processed", ["service"])

ORDERS_CREATED = Counter("orders_created_total", "Orders created")
ORDERS_REJECTED = Counter("orders_rejected_total", "Orders rejected", ["reason"])
ORDER_VALUE = Histogram(
    "orders_value_inr", "Order total value",
    buckets=(100, 500, 1000, 2500, 5000, 10000, 25000, 50000),
)
STATUS_CHANGES = Counter("orders_status_changes_total", "Order status transitions", ["to"])
UPSTREAM_CALLS = Counter(
    "orders_upstream_calls_total", "Calls to other services",
    ["target", "outcome"],
)
OUTBOX_PENDING = Gauge("orders_outbox_pending", "Events waiting to be published to Redis")
OUTBOX_PUBLISHED = Counter("orders_outbox_published_total", "Events published to Redis")
OUTBOX_ERRORS = Counter("orders_outbox_errors_total", "Failed attempts to publish events")
