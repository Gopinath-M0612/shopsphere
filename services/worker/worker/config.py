"""Fulfilment worker configuration (environment variables only)."""
import os
import socket
from dataclasses import dataclass


def _required(name: str, example: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"config error: {name} is required (example: {example})")
    return value


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"config error: {name} must be an integer, got {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"config error: {name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    service_name: str
    version: str
    log_level: str
    redis_url: str
    event_stream: str
    dead_letter_stream: str
    consumer_group: str
    consumer_name: str
    batch_size: int
    block_ms: int
    max_deliveries: int
    retry_idle_ms: int
    orders_url: str
    inventory_url: str
    internal_api_token: str
    http_timeout_seconds: float
    ship_delay_seconds: float
    ops_port: int
    chaos_error_rate: float


def load_settings() -> Settings:
    return Settings(
        service_name="worker",
        version=os.getenv("APP_VERSION", "1.0.0"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        redis_url=_required("REDIS_URL", "redis://localhost:6379/0"),
        event_stream=os.getenv("EVENT_STREAM", "orders.events"),
        dead_letter_stream=os.getenv("DEAD_LETTER_STREAM", "orders.dlq"),
        consumer_group=os.getenv("CONSUMER_GROUP", "fulfilment"),
        # in Kubernetes the pod name (= hostname) makes every replica a unique consumer
        consumer_name=os.getenv("CONSUMER_NAME", socket.gethostname()),
        batch_size=_int("BATCH_SIZE", 10),
        block_ms=_int("BLOCK_MS", 5000),
        max_deliveries=_int("MAX_DELIVERIES", 5),
        retry_idle_ms=_int("RETRY_IDLE_MS", 15000),
        orders_url=_required("ORDERS_URL", "http://localhost:8003").rstrip("/"),
        inventory_url=_required("INVENTORY_URL", "http://localhost:8002").rstrip("/"),
        internal_api_token=_required("INTERNAL_API_TOKEN", "same value as the orders service"),
        http_timeout_seconds=_float("HTTP_TIMEOUT_SECONDS", 3.0),
        ship_delay_seconds=_float("SHIP_DELAY_SECONDS", 2.0),
        ops_port=_int("OPS_PORT", 9100),
        chaos_error_rate=_float("CHAOS_ERROR_RATE", 0.0),
    )


settings = load_settings()
