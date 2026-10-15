"""Database access and a tiny migration runner.

Migrations are plain .sql files in /migrations, applied in name order once.
Applied versions are recorded in the schema_migrations table.
"""
import logging
import pathlib
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import settings
from .logging_setup import log_fields

log = logging.getLogger("orders.db")

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"

engine: Engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_pool_size,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"connect_timeout": settings.db_connect_timeout},
)


def wait_for_db(max_attempts: int = 10, delay_seconds: float = 2.0) -> None:
    """Retry the first connection so the service survives a slow database start."""
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            log.info("database reachable", extra=log_fields(attempt=attempt))
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("database not reachable yet",
                        extra=log_fields(attempt=attempt, max_attempts=max_attempts, error=str(exc)))
            if attempt == max_attempts:
                raise RuntimeError("database unreachable after retries") from exc
            time.sleep(delay_seconds)


def run_migrations() -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY,"
            " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ))
        # one migrator at a time, even with several replicas starting together
        conn.execute(text("SELECT pg_advisory_xact_lock(424203)"))
        applied = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in applied:
                continue
            log.info("applying migration", extra=log_fields(version=version))
            conn.exec_driver_sql(path.read_text())
            conn.execute(text("INSERT INTO schema_migrations(version) VALUES (:v)"), {"v": version})
    log.info("migrations complete")


def ping() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("database ping failed", extra=log_fields(error=str(exc)))
        return False
