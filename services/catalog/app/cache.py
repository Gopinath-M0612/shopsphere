"""Read-through Redis cache.

The cache is optional: if REDIS_URL is empty or Redis is down, the service
keeps working straight from the database (slower, but no outage).
"""
import json
import logging
from typing import Any, Callable, Optional

from .config import settings
from .logging_setup import log_fields
from .metrics import CACHE_EVENTS

log = logging.getLogger("catalog.cache")

_client = None
if settings.redis_url:
    import redis

    _client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)


def enabled() -> bool:
    return _client is not None


def ping() -> Optional[bool]:
    """None = cache not configured, True/False = reachable or not."""
    if _client is None:
        return None
    try:
        return bool(_client.ping())
    except Exception:  # noqa: BLE001
        return False


def get_or_load(key: str, loader: Callable[[], Any], ttl: Optional[int] = None) -> Any:
    if _client is None:
        return loader()
    try:
        cached = _client.get(key)
        if cached is not None:
            CACHE_EVENTS.labels(result="hit").inc()
            return json.loads(cached)
    except Exception as exc:  # noqa: BLE001
        CACHE_EVENTS.labels(result="error").inc()
        log.warning("cache read failed, using database", extra=log_fields(key=key, error=str(exc)))
        return loader()

    CACHE_EVENTS.labels(result="miss").inc()
    value = loader()
    try:
        _client.setex(key, ttl or settings.cache_ttl_seconds, json.dumps(value, default=str))
    except Exception as exc:  # noqa: BLE001
        CACHE_EVENTS.labels(result="error").inc()
        log.warning("cache write failed", extra=log_fields(key=key, error=str(exc)))
    return value


def invalidate(*patterns: str) -> None:
    if _client is None:
        return
    try:
        for pattern in patterns:
            for key in _client.scan_iter(match=pattern, count=100):
                _client.delete(key)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache invalidation failed", extra=log_fields(patterns=patterns, error=str(exc)))
