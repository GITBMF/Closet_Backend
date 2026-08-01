"""Showcasing API contracts.

Featured slots resolve their piece through the catalogue's real read shape
(PieceSummary) — showcasing does not define its own piece schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.catalogue.schemas import PieceSummary
from app.modules.showcasing.constants import FeaturedSlotType


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------- sponsors
class SponsorBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    logo_url: str | None = Field(default=None, max_length=500)
    link_url: str | None = Field(default=None, max_length=500)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    position: int = 0
    is_active: bool = True


class SponsorCreate(SponsorBase):
    pass


class SponsorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    logo_url: str | None = Field(default=None, max_length=500)
    link_url: str | None = Field(default=None, max_length=500)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    position: int | None = None
    is_active: bool | None = None


class SponsorOut(_ORM):
    id: uuid.UUID
    name: str
    logo_url: str | None
    link_url: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    position: int
    is_active: bool


# -------------------------------------------------------- featured slots
class FeaturedSlotCreate(BaseModel):
    slot: FeaturedSlotType
    piece_id: uuid.UUID
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class FeaturedSlotUpdate(BaseModel):
    slot: FeaturedSlotType | None = None
    piece_id: uuid.UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class FeaturedSlotOut(_ORM):
    id: int
    slot: FeaturedSlotType
    piece_id: uuid.UUID
    starts_at: datetime | None
    ends_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime


class FeaturedSlotWithPiece(FeaturedSlotOut):
    """Public/admin view: the slot plus the resolved catalogue piece."""

    piece: PieceSummary | None = None


# --------------------------------------------------------- combined home
class HomeShowcase(BaseModel):
    sponsors: list[SponsorOut]
    featured: list[FeaturedSlotWithPiece]