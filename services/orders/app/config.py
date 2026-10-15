"""Orders service configuration (environment variables only)."""
import os
from dataclasses import dataclass


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


def _required(name: str, example: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"config error: {name} is required (example: {example})")
    return value


@dataclass(frozen=True)
class Settings:
    service_name: str
    version: str
    port: int
    log_level: str
    database_url: str
    db_pool_size: int
    db_connect_timeout: int
    run_migrations: bool
    catalog_url: str
    inventory_url: str
    http_timeout_seconds: float
    http_retries: int
    redis_url: str
    event_stream: str
    outbox_interval_seconds: float
    internal_api_token: str
    currency: str
    max_items_per_order: int
    chaos_error_rate: float
    chaos_latency_ms: int


def load_settings() -> Settings:
    database_url = _required("DATABASE_URL", "postgresql://orders:orders@localhost:5432/orders")
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg2://" + database_url[len("postgresql://"):]
    return Settings(
        service_name="orders",
        version=os.getenv("APP_VERSION", "1.0.0"),
        port=_int("PORT", 8003),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        database_url=database_url,
        db_pool_size=_int("DB_POOL_SIZE", 5),
        db_connect_timeout=_int("DB_CONNECT_TIMEOUT", 5),
        run_migrations=os.getenv("RUN_MIGRATIONS", "true").lower() == "true",
        catalog_url=_required("CATALOG_URL", "http://localhost:8001").rstrip("/"),
        inventory_url=_required("INVENTORY_URL", "http://localhost:8002").rstrip("/"),
        http_timeout_seconds=_float("HTTP_TIMEOUT_SECONDS", 3.0),
        http_retries=_int("HTTP_RETRIES", 2),
        redis_url=_required("REDIS_URL", "redis://localhost:6379/0"),
        event_stream=os.getenv("EVENT_STREAM", "orders.events"),
        outbox_interval_seconds=_float("OUTBOX_INTERVAL_SECONDS", 2.0),
        internal_api_token=_required("INTERNAL_API_TOKEN", "change-me-long-random-string"),
        currency=os.getenv("CURRENCY", "INR"),
        max_items_per_order=_int("MAX_ITEMS_PER_ORDER", 20),
        chaos_error_rate=_float("CHAOS_ERROR_RATE", 0.0),
        chaos_latency_ms=_int("CHAOS_LATENCY_MS", 0),
    )


settings = load_settings()
