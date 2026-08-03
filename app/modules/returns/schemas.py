"""Returns API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.returns.constants import ReturnStatus


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReturnCreate(BaseModel):
    purchase_id: uuid.UUID
    piece_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=1000)


class ReturnOut(_ORM):
    id: uuid.UUID
    purchase_id: uuid.UUID
    piece_id: uuid.UUID
    reason: str | None
    status: ReturnStatus
    resolution_note: str | None
    restocked: bool
    created_by: uuid.UUID | None
    created_at: datetime


class ReturnsPage(BaseModel):
    items: list[ReturnOut]
    total: int
    limit: int
    offset: int


class ApproveIn(BaseModel):
    """Approve a return and issue a refund.

    If amount is omitted, the piece's line price from the purchase is refunded.
    """

    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)


class ResolveIn(BaseModel):
    restock: bool = True
    note: str | None = Field(default=None, max_length=500)