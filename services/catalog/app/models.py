"""Request and response schemas."""
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class CategoryIn(BaseModel):
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=100)


class CategoryOut(CategoryIn):
    id: int
    product_count: int = 0


class ProductIn(BaseModel):
    sku: str = Field(min_length=3, max_length=40, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    category_slug: str
    image_url: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    price: Optional[Decimal] = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    category_slug: Optional[str] = None
    image_url: Optional[str] = None
    active: Optional[bool] = None


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    description: str
    price: float
    category: str
    image_url: Optional[str]
    active: bool


class ProductPage(BaseModel):
    items: List[ProductOut]
    page: int
    page_size: int
    total: int
