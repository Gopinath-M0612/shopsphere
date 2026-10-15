"""Liveness, readiness and metrics."""
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

from .. import clients, db, outbox, repository
from ..config import settings

router = APIRouter(tags=["ops"])

ORDERS_BY_STATUS = Gauge("orders_by_status", "Orders currently in each status", ["status"])


@router.get("/health")
def health():
    """Liveness: the process is up. Never checks dependencies."""
    return {"status": "ok", "service": settings.service_name, "version": settings.version}


@router.get("/ready")
def ready():
    """Readiness depends on OUR database only.

    Redis down  -> events wait in the outbox (degraded, still ready).
    Catalog/inventory down -> new orders fail with 503, but reads still work,
    so we must not take this pod out of service for someone else's outage.
    """
    db_ok = db.ping()
    body = {
        "status": "ready" if db_ok else "not-ready",
        "checks": {
            "database": "ok" if db_ok else "fail",
            "event_bus": "ok" if outbox.redis_ok() else "degraded",
            "catalog": "ok" if clients.health(settings.catalog_url) else "unreachable",
            "inventory": "ok" if clients.health(settings.inventory_url) else "unreachable",
        },
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)


@router.get("/metrics")
def metrics():
    try:
        with db.engine.connect() as conn:
            for status, count in repository.status_counts(conn).items():
                ORDERS_BY_STATUS.labels(status).set(count)
    except Exception:  # noqa: BLE001
        pass
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
