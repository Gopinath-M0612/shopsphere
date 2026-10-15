"""ShopSphere Catalog service: products and categories."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db
from .config import settings
from .logging_setup import log_fields, setup_logging
from .middleware import RequestContextMiddleware
from .routes import categories, health, products

setup_logging(settings.service_name, settings.version, settings.log_level)
log = logging.getLogger("catalog")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("starting", extra=log_fields(port=settings.port, cache=bool(settings.redis_url),
                                          chaos_error_rate=settings.chaos_error_rate,
                                          chaos_latency_ms=settings.chaos_latency_ms))
    db.wait_for_db()
    if settings.run_migrations:
        db.run_migrations()
    yield
    log.info("shutting down, closing database pool")
    db.engine.dispose()


app = FastAPI(title="ShopSphere Catalog", version=settings.version, lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.include_router(health.router)
app.include_router(categories.router)
app.include_router(products.router)
