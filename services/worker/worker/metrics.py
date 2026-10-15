"""Prometheus metrics for the worker."""
from prometheus_client import Counter, Gauge, Histogram

EVENTS = Counter("worker_events_total", "Events processed", ["type", "outcome"])
PROCESSING = Histogram(
    "worker_event_duration_seconds", "Time to handle one event", ["type"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
DEAD_LETTERED = Counter("worker_dead_lettered_total", "Events moved to the dead-letter stream", ["type"])
PENDING = Gauge("worker_pending_events", "Events delivered but not yet acknowledged")
LAG = Gauge("worker_stream_length", "Total events in the stream")
EMAILS = Counter("worker_emails_sent_total", "Notification emails sent", ["template"])
LAST_SUCCESS = Gauge("worker_last_success_timestamp_seconds", "Unix time of the last successful event")
