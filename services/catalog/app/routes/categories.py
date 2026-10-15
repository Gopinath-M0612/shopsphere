"""Category endpoints."""
import logging
from typing import List

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .. import cache, db
from ..logging_setup import log_fields
from ..models import CategoryIn, CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])
log = logging.getLogger("catalog.categories")


def _load_categories() -> list:
    with db.engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT c.id, c.slug, c.name, count(p.id) FILTER (WHERE p.active) AS product_count "
            "FROM categories c LEFT JOIN products p ON p.category_id = c.id "
            "GROUP BY c.id ORDER BY c.name"
        )).mappings().all()
    return [dict(r) for r in rows]


@router.get("", response_model=List[CategoryOut])
def list_categories():
    return cache.get_or_load("catalog:categories", _load_categories)


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn):
    try:
        with db.engine.begin() as conn:
            row = conn.execute(
                text("INSERT INTO categories(slug, name) VALUES (:slug, :name) RETURNING id, slug, name"),
                body.model_dump(),
            ).mappings().one()
    except IntegrityError:
        raise HTTPException(409, f"category '{body.slug}' already exists")
    cache.invalidate("catalog:categories")
    log.info("category created", extra=log_fields(slug=body.slug))
    return {**row, "product_count": 0}
