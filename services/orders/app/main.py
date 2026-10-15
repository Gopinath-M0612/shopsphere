"""ShopSphere Orders service: order lifecycle + event outbox."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import clients, db, outbox
from .config import settings
from .logging_setup import log_fields, setup_logging
from .middleware import RequestContextMiddleware
from .routes import health, internal, orders

setup_logging(settings.service_name, settings.version, settings.log_level)
log = logging.getLogger("orders")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("starting", extra=log_fields(
        port=settings.port, catalog_url=settings.catalog_url, inventory_url=settings.inventory_url,
        event_stream=settings.event_stream, chaos_error_rate=settings.chaos_error_rate,
        chaos_latency_ms=settings.chaos_latency_ms))
    db.wait_for_db()
    if settings.run_migrations:
        db.run_migrations()
    outbox.start()
    yield
    log.info("shutting down: stopping outbox relay and closing pools")
    outbox.stop()
    clients.close()
    db.engine.dispose()


app = FastAPI(title="ShopSphere Orders", version=settings.version, lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.include_router(health.router)
app.include_router(orders.router)
app.include_router(internal.router)
