"""Redis Streams consumer loop with retries and a dead-letter stream.

- XREADGROUP gives each event to exactly one worker replica.
- An event is XACKed only after it was handled successfully.
- Events left unacknowledged (crash, timeout, retryable error) are re-claimed
  with XAUTOCLAIM after RETRY_IDLE_MS and tried again.
- After MAX_DELIVERIES attempts an event goes to the dead-letter stream.
"""
import json
import logging
import time

import redis

from . import handlers, logs
from .config import settings
from .metrics import DEAD_LETTERED, EVENTS, LAG, LAST_SUCCESS, PENDING, PROCESSING

log = logging.getLogger("worker.consumer")


class Consumer:
    def __init__(self):
        self.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True,
                                          socket_timeout=(settings.block_ms / 1000) + 5,
                                          socket_connect_timeout=3)
        self.running = True

    # ---------- setup ----------
    def ensure_group(self) -> None:
        try:
            self.redis.xgroup_create(settings.event_stream, settings.consumer_group, id="0", mkstream=True)
            log.info("consumer group created", extra=logs.fields(
                stream=settings.event_stream, group=settings.consumer_group))
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def ping(self) -> bool:
        try:
            return bool(self.redis.ping())
        except Exception:  # noqa: BLE001
            return False

    # ---------- processing ----------
    def _delivery_count(self, message_id: str) -> int:
        info = self.redis.xpending_range(settings.event_stream, settings.consumer_group,
                                         min=message_id, max=message_id, count=1)
        return info[0]["times_delivered"] if info else 1

    def _dead_letter(self, message_id: str, fields: dict, reason: str) -> None:
        self.redis.xadd(settings.dead_letter_stream, {
            **fields, "original_id": message_id, "failed_reason": reason[:500],
            "failed_at": str(int(time.time())),
        })
        self.redis.xack(settings.event_stream, settings.consumer_group, message_id)
        DEAD_LETTERED.labels(fields.get("type", "unknown")).inc()
        log.error("event moved to dead-letter stream", extra=logs.fields(
            message_id=message_id, type=fields.get("type"), reason=reason))

    def handle(self, message_id: str, fields: dict) -> None:
        event_type = fields.get("type", "unknown")
        start = time.perf_counter()
        try:
            data = json.loads(fields.get("data", "{}"))
            handled = handlers.dispatch(event_type, data)
        except handlers.PermanentError as exc:
            EVENTS.labels(event_type, "permanent_error").inc()
            self._dead_letter(message_id, fields, str(exc))
            return
        except (handlers.RetryableError, redis.RedisError) as exc:
            EVENTS.labels(event_type, "retryable_error").inc()
            attempts = self._delivery_count(message_id)
            if attempts >= settings.max_deliveries:
                self._dead_letter(message_id, fields, f"gave up after {attempts} attempts: {exc}")
            else:
                log.warning("event failed, will retry", extra=logs.fields(
                    message_id=message_id, type=event_type, attempt=attempts,
                    max_deliveries=settings.max_deliveries, error=str(exc)))
            return
        except json.JSONDecodeError as exc:
            EVENTS.labels(event_type, "bad_payload").inc()
            self._dead_letter(message_id, fields, f"invalid JSON: {exc}")
            return
        except Exception as exc:  # noqa: BLE001  unexpected bug: retry, then dead-letter
            EVENTS.labels(event_type, "crash").inc()
            log.exception("unexpected error handling event", extra=logs.fields(message_id=message_id))
            if self._delivery_count(message_id) >= settings.max_deliveries:
                self._dead_letter(message_id, fields, f"unexpected error: {exc}")
            return

        self.redis.xack(settings.event_stream, settings.consumer_group, message_id)
        EVENTS.labels(event_type, "ok" if handled else "ignored").inc()
        PROCESSING.labels(event_type).observe(time.perf_counter() - start)
        LAST_SUCCESS.set(time.time())
        log.info("event processed", extra=logs.fields(
            message_id=message_id, type=event_type, handled=handled,
            duration_ms=round((time.perf_counter() - start) * 1000, 1)))

    def reclaim(self) -> int:
        """Pick up events another (possibly dead) consumer never acknowledged."""
        _next, messages, *_ = self.redis.xautoclaim(
            settings.event_stream, settings.consumer_group, settings.consumer_name,
            min_idle_time=settings.retry_idle_ms, start_id="0-0", count=settings.batch_size)
        for message_id, fields in messages:
            if fields is None:  # deleted from the stream meanwhile
                self.redis.xack(settings.event_stream, settings.consumer_group, message_id)
                continue
            log.info("retrying stuck event", extra=logs.fields(message_id=message_id, type=fields.get("type")))
            self.handle(message_id, fields)
        return len(messages)

    def update_gauges(self) -> None:
        try:
            summary = self.redis.xpending(settings.event_stream, settings.consumer_group)
            PENDING.set(summary["pending"])
            LAG.set(self.redis.xlen(settings.event_stream))
        except redis.RedisError:
            pass

    # ---------- main loop ----------
    def run(self) -> None:
        self.ensure_group()
        log.info("consuming", extra=logs.fields(
            stream=settings.event_stream, group=settings.consumer_group, consumer=settings.consumer_name))
        last_reclaim = 0.0
        while self.running:
            try:
                if time.monotonic() - last_reclaim > settings.retry_idle_ms / 1000:
                    self.reclaim()
                    self.update_gauges()
                    last_reclaim = time.monotonic()
                batches = self.redis.xreadgroup(
                    settings.consumer_group, settings.consumer_name, {settings.event_stream: ">"},
                    count=settings.batch_size, block=settings.block_ms)
                for _stream, messages in batches or []:
                    for message_id, fields in messages:
                        if not self.running:
                            break  # unacked events are re-claimed by another replica
                        self.handle(message_id, fields)
            except redis.ConnectionError as exc:
                log.error("redis unavailable, retrying in 3s", extra=logs.fields(error=str(exc)))
                time.sleep(3)
            except redis.ResponseError as exc:
                if "NOGROUP" in str(exc):
                    log.warning("consumer group missing (stream deleted?), recreating")
                    self.ensure_group()
                else:
                    raise
        log.info("consumer loop stopped")

    def stop(self) -> None:
        self.running = False
