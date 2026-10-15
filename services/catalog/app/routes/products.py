"""Product endpoints: list/search with pagination, lookup by id or SKU, create, update."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .. import cache, db
from ..logging_setup import log_fields
from ..models import ProductIn, ProductOut, ProductPage, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])
log = logging.getLogger("catalog.products")

SELECT_PRODUCT = (
    "SELECT p.id, p.sku, p.name, p.description, p.price::float AS price, "
    "c.slug AS category, p.image_url, p.active "
    "FROM products p JOIN categories c ON c.id = p.category_id "
)


def _category_id(conn, slug: str) -> int:
    cid = conn.execute(text("SELECT id FROM categories WHERE slug = :s"), {"s": slug}).scalar()
    if cid is None:
        raise HTTPException(422, f"unknown category '{slug}'")
    return cid


@router.get("", response_model=ProductPage)
def list_products(
    q: Optional[str] = Query(default=None, max_length=100, description="search in name/description"),
    category: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_inactive: bool = False,
):
    key = f"catalog:products:{q}:{category}:{page}:{page_size}:{include_inactive}"

    def load():
        where, params = [], {}
        if not include_inactive:
            where.append("p.active")
        if category:
            where.append("c.slug = :category")
            params["category"] = category
        if q:
            where.append("(p.name ILIKE :q OR p.description ILIKE :q)")
            params["q"] = f"%{q}%"
        clause = ("WHERE " + " AND ".join(where) + " ") if where else ""
        with db.engine.connect() as conn:
            total = conn.execute(
                text("SELECT count(*) FROM products p JOIN categories c ON c.id = p.category_id " + clause),
                params,
            ).scalar_one()
            rows = conn.execute(
                text(SELECT_PRODUCT + clause + "ORDER BY p.id LIMIT :limit OFFSET :offset"),
                {**params, "limit": page_size, "offset": (page - 1) * page_size},
            ).mappings().all()
        return {"items": [dict(r) for r in rows], "page": page, "page_size": page_size, "total": total}

    return cache.get_or_load(key, load)


@router.get("/by-sku/{sku}", response_model=ProductOut)
def get_by_sku(sku: str):
    def load():
        with db.engine.connect() as conn:
            row = conn.execute(text(SELECT_PRODUCT + "WHERE p.sku = :sku"), {"sku": sku}).mappings().first()
        return dict(row) if row else None

    product = cache.get_or_load(f"catalog:sku:{sku}", load)
    if product is None:
        raise HTTPException(404, f"product '{sku}' not found")
    return product


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int):
    with db.engine.connect() as conn:
        row = conn.execute(text(SELECT_PRODUCT + "WHERE p.id = :id"), {"id": product_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "product not found")
    return dict(row)


@router.post("", response_model=ProductOut, status_code=201)
def create_product(body: ProductIn):
    try:
        with db.engine.begin() as conn:
            cid = _category_id(conn, body.category_slug)
            new_id = conn.execute(
                text("INSERT INTO products(sku, name, description, price, category_id, image_url, active) "
                     "VALUES (:sku, :name, :description, :price, :cid, :image_url, :active) RETURNING id"),
                {**body.model_dump(exclude={"category_slug"}), "cid": cid},
            ).scalar_one()
            row = conn.execute(text(SELECT_PRODUCT + "WHERE p.id = :id"), {"id": new_id}).mappings().one()
    except IntegrityError:
        raise HTTPException(409, f"sku '{body.sku}' already exists")
    cache.invalidate("catalog:products:*", "catalog:categories")
    log.info("product created", extra=log_fields(sku=body.sku, price=str(body.price)))
    return dict(row)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductUpdate):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "nothing to update")
    with db.engine.begin() as conn:
        if "category_slug" in changes:
            changes["category_id"] = _category_id(conn, changes.pop("category_slug"))
        sets = ", ".join(f"{col} = :{col}" for col in changes)
        updated = conn.execute(
            text(f"UPDATE products SET {sets}, updated_at = now() WHERE id = :id RETURNING sku"),
            {**changes, "id": product_id},
        ).scalar()
        if updated is None:
            raise HTTPException(404, "product not found")
        row = conn.execute(text(SELECT_PRODUCT + "WHERE p.id = :id"), {"id": product_id}).mappings().one()
    cache.invalidate("catalog:products:*", "catalog:categories", f"catalog:sku:{updated}")
    log.info("product updated", extra=log_fields(id=product_id, fields=list(changes)))
    return dict(row)
