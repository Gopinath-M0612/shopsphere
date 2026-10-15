"""Transactional outbox.

Events are written to the `outbox` table in the SAME database transaction as the
order. A background thread then publishes them to the Redis stream. If Redis is
down, orders are still accepted and events wait in the table until it is back.
"""
import json
import logging
import threading

import redis
from sqlalchemy import text

from . import db
from .config import settings
from .logging_setup import log_fields
from .metrics import OUTBOX_ERRORS, OUTBOX_PENDING, OUTBOX_PUBLISHED

log = logging.getLogger("orders.outbox")

_redis = redis.Redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)
_wakeup = threading.Event()
_stop = threading.Event()
_thread = None


def add_event(conn, event_type: str, payload: dict) -> None:
    """Call inside an open transaction."""
    conn.execute(
        text("INSERT INTO outbox(event_type, payload) VALUES (:t, CAST(:p AS JSONB))"),
        {"t": event_type, "p": json.dumps(payload, default=str)},
    )


def notify() -> None:
    _wakeup.set()


def redis_ok() -> bool:
    try:
        return bool(_redis.ping())
    except Exception:  # noqa: BLE001
        return False


def publish_batch(limit: int = 50) -> int:
    published = 0
    with db.engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT id, event_type, payload FROM outbox WHERE published_at IS NULL "
            "ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED"), {"limit": limit}).mappings().all()
        for row in rows:
            payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
            try:
                _redis.xadd(settings.event_stream, {
                    "event_id": str(row["id"]),
                    "type": row["event_type"],
                    "data": json.dumps(payload, default=str),
                }, maxlen=100_000, approximate=True)
            except Exception as exc:  # noqa: BLE001
                OUTBOX_ERRORS.inc()
                log.warning("event publish failed, will retry", extra=log_fields(
                    event_id=row["id"], type=row["event_type"], error=str(exc)))
                break
            conn.execute(text("UPDATE outbox SET published_at = now() WHERE id = :id"), {"id": row["id"]})
            published += 1
        pending = conn.execute(text("SELECT count(*) FROM outbox WHERE published_at IS NULL")).scalar_one()
    OUTBOX_PENDING.set(pending - published if pending >= published else 0)
    if published:
        OUTBOX_PUBLISHED.inc(published)
        log.info("events published", extra=log_fields(count=published, stream=settings.event_stream))
    return published


def _loop() -> None:
    log.info("outbox relay started", extra=log_fields(interval_s=settings.outbox_interval_seconds))
    while not _stop.is_set():
        try:
            publish_batch()
        except Exception as exc:  # noqa: BLE001
            OUTBOX_ERRORS.inc()
            log.error("outbox relay error", extra=log_fields(error=str(exc)))
        _wakeup.wait(settings.outbox_interval_seconds)
        _wakeup.clear()
    log.info("outbox relay stopped")


def start() -> None:
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="outbox-relay", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
    _wakeup.set()
    if _thread:
        _thread.join(timeout=5)
