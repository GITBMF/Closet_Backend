"""Order API contracts.

Checkout accepts a cart of piece IDs plus contact + delivery destination.
The backend snapshots title/price per item and the address, so later edits to
a piece or a saved address never rewrite order history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.identity.constants import ActorType
from app.modules.orders.constants import OrderStatus


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------- checkout in
class AddressIn(BaseModel):
    """Delivery address. Snapshotted onto the order as JSON."""

    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    neighbourhood: str | None = Field(default=None, max_length=120)
    landmark: str | None = Field(default=None, max_length=200)
    city_id: int | None = None
    region_id: int | None = None


class CheckoutIn(BaseModel):
    piece_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    customer_name: str = Field(min_length=2, max_length=150)
    customer_phone: str = Field(min_length=6, max_length=32)
    customer_email: EmailStr | None = None
    address: AddressIn
    customer_note: str | None = Field(default=None, max_length=2000)
    privilege_code: str | None = Field(default=None, max_length=40)


# ----------------------------------------------------------------- outputs
class OrderItemOut(_ORMModel):
    piece_id: uuid.UUID
    title: str
    price: Decimal


class StatusHistoryOut(_ORMModel):
    """One entry in an order's status timeline."""

    from_status: OrderStatus | None
    to_status: OrderStatus
    actor_type: ActorType
    actor_id: uuid.UUID | None
    reason: str | None
    created_at: datetime


class OrderOut(_ORMModel):
    id: uuid.UUID
    order_number: str
    status: OrderStatus
    customer_name: str
    customer_phone: str
    customer_email: str | None
    delivery_address: dict | None
    delivery_city_id: int | None
    delivery_region_id: int | None
    subtotal: Decimal
    delivery_fee: Decimal
    discount_amount: Decimal
    total: Decimal
    currency: str
    quote_required: bool
    customer_note: str | None
    admin_note: str | None
    placed_at: datetime | None
    created_at: datetime
    items: list[OrderItemOut] = []


class OrderSummary(_ORMModel):
    """Trimmed shape for list views."""

    id: uuid.UUID
    order_number: str
    status: OrderStatus
    customer_name: str
    total: Decimal
    currency: str
    quote_required: bool
    created_at: datetime


class OrdersPage(BaseModel):
    items: list[OrderSummary]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------- admin writes
class StatusUpdate(BaseModel):
    status: OrderStatus
    reason: str | None = Field(default=None, max_length=500)


class ManualQuote(BaseModel):
    """Set a delivery fee for an out-of-zone (quote_required) order."""

    delivery_fee: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    admin_note: str | None = Field(default=None, max_length=500)