"""Request and response schemas."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .config import settings

OrderStatus = Literal["PENDING", "CONFIRMED", "SHIPPED", "CANCELLED"]


class OrderItemIn(BaseModel):
    sku: str = Field(pattern=r"^[A-Z0-9-]{3,40}$")
    qty: int = Field(ge=1, le=100)


class OrderIn(BaseModel):
    customer_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    items: List[OrderItemIn] = Field(min_length=1, max_length=settings.max_items_per_order)


class OrderItemOut(BaseModel):
    sku: str
    name: str
    unit_price: float
    qty: int
    line_total: float


class OrderOut(BaseModel):
    id: str
    customer_email: str
    status: OrderStatus
    total: float
    currency: str
    cancel_reason: Optional[str] = None
    created_at: str
    updated_at: str
    items: List[OrderItemOut] = []


class StatusChange(BaseModel):
    status: OrderStatus
    reason: Optional[str] = Field(default=None, max_length=200)


class CancelIn(BaseModel):
    reason: Optional[str] = Field(default="cancelled by customer", max_length=200)
