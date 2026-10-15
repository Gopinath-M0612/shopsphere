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
CACHE_EVENTS = Counter("catalog_cache_events_total", "Cache hits, misses and errors", ["result"])
PRODUCTS_TOTAL = Gauge("catalog_products_total", "Active products in the catalog")
