"""Liveness, readiness and metrics endpoints (used by Kubernetes and Prometheus)."""
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from .. import cache, db
from ..config import settings
from ..metrics import PRODUCTS_TOTAL

router = APIRouter(tags=["ops"])


@router.get("/health")
def health():
    """Liveness: the process is up. Never checks dependencies."""
    return {"status": "ok", "service": settings.service_name, "version": settings.version}


@router.get("/ready")
def ready():
    """Readiness: can this replica serve traffic right now?"""
    db_ok = db.ping()
    cache_state = cache.ping()
    body = {
        "status": "ready" if db_ok else "not-ready",
        "checks": {
            "database": "ok" if db_ok else "fail",
            "cache": {None: "disabled", True: "ok", False: "degraded"}[cache_state],
        },
    }
    # the cache is optional: a broken cache degrades speed but must not remove the pod
    return JSONResponse(body, status_code=200 if db_ok else 503)


@router.get("/metrics")
def metrics():
    try:
        with db.engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM products WHERE active")).scalar_one()
        PRODUCTS_TOTAL.set(count)
    except Exception:  # noqa: BLE001
        pass
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
