from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.modules.catalogue.schemas import PieceResponse


# --- Sponsor Schemas ---
class SponsorBase(BaseModel):
    name: str
    logo_url: str
    link_url: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    is_active: bool = True


class SponsorCreate(SponsorBase):
    pass


class SponsorUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    link_url: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class SponsorResponse(SponsorBase):
    id: UUID

    model_config = ConfigDict(from_attributes=True)


# --- Featured Slot Schemas ---
class FeaturedSlotBase(BaseModel):
    slot_type: str
    piece_id: UUID
    position: int = 0
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class FeaturedSlotCreate(FeaturedSlotBase):
    pass


class FeaturedSlotUpdate(BaseModel):
    slot_type: Optional[str] = None
    piece_id: Optional[UUID] = None
    position: Optional[int] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class FeaturedSlotResponse(FeaturedSlotBase):
    id: int
    created_by: Optional[UUID] = None
    piece: Optional[PieceResponse] = None  # Inclusion de la pièce lue depuis Catalogue

    model_config = ConfigDict(from_attributes=True)


# --- Home Showcase Combined Schema ---
class HomeShowcaseResponse(BaseModel):
    sponsors: List[SponsorResponse]
    featured_slots: List[FeaturedSlotResponse]