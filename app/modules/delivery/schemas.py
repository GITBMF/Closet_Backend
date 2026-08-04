"""Delivery API contracts.

The courier-link token is special: the RAW token is returned exactly once, when
the link is created (LinkOut.token). It is never stored or shown again — only its
hash lives in the database. Everything the courier does carries that raw token in
the URL; there is no JWT on the courier endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.delivery.constants import DeliveryStatus


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------- couriers
class CourierIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=6, max_length=32)


class CourierOut(_ORM):
    id: uuid.UUID
    full_name: str
    phone: str
    is_active: bool
    created_at: datetime


# ------------------------------------------------------------ deliveries
class CreateDeliveryIn(BaseModel):
    order_number: str = Field(min_length=3, max_length=40)
    courier_id: uuid.UUID | None = None   # assign now, or leave unassigned


class AssignIn(BaseModel):
    courier_id: uuid.UUID


class DeliveryOut(_ORM):
    id: uuid.UUID
    purchase_id: uuid.UUID
    courier_id: uuid.UUID | None
    status: DeliveryStatus
    failure_reason: str | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class DeliverySummary(_ORM):
    id: uuid.UUID
    purchase_id: uuid.UUID
    courier_id: uuid.UUID | None
    status: DeliveryStatus
    created_at: datetime


class DeliveriesPage(BaseModel):
    items: list[DeliverySummary]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------- admin status edit
class AdminStatusIn(BaseModel):
    status: DeliveryStatus
    reason: str | None = Field(default=None, max_length=500)


# ------------------------------------------------------------- events
class EventOut(_ORM):
    id: uuid.UUID
    status: DeliveryStatus
    reason: str | None
    source: str | None
    created_at: datetime


# ------------------------------------------------------- courier links
class LinkIn(BaseModel):
    ttl_hours: int = Field(default=24, ge=1, le=168)     # up to a week
    max_uses: int = Field(default=100, ge=1, le=1000)


class LinkOut(_ORM):
    id: uuid.UUID
    delivery_id: uuid.UUID
    token: str            # RAW token — returned ONCE, never again
    expires_at: datetime
    max_uses: int


# --------------------------------------------- what the courier sees/does
class CourierDeliveryView(BaseModel):
    """Minimal, courier-safe view — no internal ids, no customer PII beyond
    what a courier needs to deliver."""

    order_number: str
    status: DeliveryStatus
    customer_name: str
    customer_phone: str | None
    delivery_address: dict | None
    items_count: int


class CourierStatusIn(BaseModel):
    status: DeliveryStatus
    reason: str | None = Field(default=None, max_length=500)