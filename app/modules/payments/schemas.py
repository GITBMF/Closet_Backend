"""Payment API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.payments.constants import PaymentStatus


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------- initiate
class InitiateIn(BaseModel):
    order_number: str = Field(min_length=3, max_length=40)
    # optional customer contact overrides (guests); fall back to the order's
    customer_phone: str | None = Field(default=None, max_length=32)
    customer_email: str | None = Field(default=None, max_length=255)
    operator: str | None = Field(default=None, max_length=40)  # mtn_momo, orange_money


class InitiateOut(_ORMModel):
    id: uuid.UUID
    status: PaymentStatus
    amount: Decimal
    currency: str
    payment_url: str | None
    provider_reference: str | None


# ------------------------------------------------------------------ reads
class PaymentOut(_ORMModel):
    id: uuid.UUID
    purchase_id: uuid.UUID
    status: PaymentStatus
    amount: Decimal
    currency: str
    operator: str | None
    provider_reference: str | None
    payer_phone: str | None
    failure_reason: str | None
    initiated_at: datetime | None
    confirmed_at: datetime | None
    reconciled_at: datetime | None
    created_at: datetime


class PaymentSummary(_ORMModel):
    id: uuid.UUID
    purchase_id: uuid.UUID
    status: PaymentStatus
    amount: Decimal
    currency: str
    provider_reference: str | None
    created_at: datetime


class PaymentsPage(BaseModel):
    items: list[PaymentSummary]
    total: int
    limit: int
    offset: int


# ----------------------------------------------------------- admin writes
class ReconcileIn(BaseModel):
    """Manually mark a payment succeeded/failed after an out-of-band check."""

    status: PaymentStatus
    note: str | None = Field(default=None, max_length=500)


class RefundIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reason: str | None = Field(default=None, max_length=500)


class RefundOut(_ORMModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    amount: Decimal
    reason: str | None
    provider_reference: str | None
    created_at: datetime


class WebhookAck(BaseModel):
    received: bool = True