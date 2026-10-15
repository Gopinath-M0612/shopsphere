"""Catalog service configuration.

Every setting comes from an environment variable so the same image can run
in dev, staging and prod. Nothing here should ever contain a real password.
"""
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


@dataclass(frozen=True)
class Settings:
    service_name: str
    version: str
    port: int
    log_level: str
    database_url: str
    db_pool_size: int
    db_connect_timeout: int
    redis_url: str
    cache_ttl_seconds: int
    run_migrations: bool
    chaos_error_rate: float
    chaos_latency_ms: int


def load_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("config error: DATABASE_URL is required "
                           "(example: postgresql://catalog:catalog@localhost:5432/catalog)")
    # use the psycopg2 driver explicitly, whatever SQLAlchemy's default is
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg2://" + database_url[len("postgresql://"):]
    return Settings(
        service_name="catalog",
        version=os.getenv("APP_VERSION", "1.0.0"),
        port=_int("PORT", 8001),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        database_url=database_url,
        db_pool_size=_int("DB_POOL_SIZE", 5),
        db_connect_timeout=_int("DB_CONNECT_TIMEOUT", 5),
        redis_url=os.getenv("REDIS_URL", ""),
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 60),
        run_migrations=os.getenv("RUN_MIGRATIONS", "true").lower() == "true",
        chaos_error_rate=_float("CHAOS_ERROR_RATE", 0.0),
        chaos_latency_ms=_int("CHAOS_LATENCY_MS", 0),
    )


settings = load_settings()
