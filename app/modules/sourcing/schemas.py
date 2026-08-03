"""Sourcing API contracts (applications, submissions, review, payouts)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.sourcing.constants import (
    CollaborationType,
    CollectionMethod,
    PayoutStatus,
    SourcerStatus,
    SubmissionStatus,
)


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------- applications
class ApplyIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=32)
    collaboration_type: CollaborationType | None = None
    payout_method: str | None = Field(default=None, max_length=40)
    payout_phone: str | None = Field(default=None, max_length=32)


class SourcerProfileOut(_ORM):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str | None
    phone: str | None
    status: SourcerStatus
    collaboration_type: CollaborationType | None
    rejection_reason: str | None
    approved_at: datetime | None
    payout_method: str | None
    payout_phone: str | None
    is_featured: bool
    created_at: datetime


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


# --------------------------------------------------------- submissions
class SubmissionCreate(BaseModel):
    item_type: str | None = Field(default=None, max_length=80)
    brand: str | None = Field(default=None, max_length=120)
    size_label: str | None = Field(default=None, max_length=32)
    condition_claimed: str | None = Field(default=None, max_length=40)
    desired_price: Decimal | None = Field(default=None, ge=0)
    story: str | None = None
    share_permission: bool = False
    collection_method: CollectionMethod | None = None


class MediaIn(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    position: int = 0


class MediaOut(_ORM):
    id: uuid.UUID
    url: str
    position: int


class SubmissionOut(_ORM):
    id: uuid.UUID
    sourcer_id: uuid.UUID
    item_type: str | None
    brand: str | None
    size_label: str | None
    condition_claimed: str | None
    desired_price: Decimal | None
    story: str | None
    share_permission: bool
    status: SubmissionStatus
    refusal_reason: str | None
    collection_method: CollectionMethod | None
    piece_id: uuid.UUID | None
    created_at: datetime
    media: list[MediaOut] = []


class SubmissionSummary(_ORM):
    id: uuid.UUID
    sourcer_id: uuid.UUID
    item_type: str | None
    brand: str | None
    status: SubmissionStatus
    created_at: datetime


class SubmissionsPage(BaseModel):
    items: list[SubmissionSummary]
    total: int
    limit: int
    offset: int


# --------------------------------------------------- admin decisions
class DecisionIn(BaseModel):
    accept: bool
    reason: str | None = Field(default=None, max_length=500)  # required if refusing


class CatalogueIn(BaseModel):
    """Turn an accepted submission into a catalogue piece."""

    title: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(ge=0)
    condition: str = Field(description="catalogue PieceCondition value")
    size_label: str | None = Field(default=None, max_length=32)
    house_id: uuid.UUID | None = None
    universe_id: uuid.UUID | None = None


# --------------------------------------------------------- payouts
class PayoutOut(_ORM):
    id: uuid.UUID
    sourcer_id: uuid.UUID
    amount: Decimal
    currency: str
    status: PayoutStatus
    method: str | None
    provider_reference: str | None
    paid_at: datetime | None
    created_at: datetime