"""Catalogue API contracts.

Public browse/search/detail reads, plus admin write models for the piece
lifecycle, media, houses, universes and publication batches.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.catalogue.constants import (
    AcquisitionType,
    MediaType,
    PieceCondition,
    PieceStatus,
)

# Reusable text constraints: trim surrounding whitespace, then enforce a real
# minimum so blank / single-character junk ("a", "   ") can't be saved. Applied
# to write models only; the *Out/detail models echo stored values unchanged.
TitleText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
BlurbText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=1000)]
StoryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=2000)]


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------- houses / universes
class HouseOut(_ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool


class HouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=140)
    is_active: bool = True


class UniverseOut(_ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    position: int
    is_active: bool


class UniverseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=140)
    position: int = 0
    is_active: bool = True


# ------------------------------------------------------------------- media
class MediaOut(_ORMModel):
    id: uuid.UUID
    media_type: MediaType
    url: str
    view_label: str | None
    position: int


class MediaMeta(BaseModel):
    """Optional metadata sent as form fields alongside the uploaded file.

    The file itself arrives as multipart/form-data; the backend uploads it to
    object storage and derives the URL — the client never supplies a URL.
    """

    view_label: str | None = Field(default=None, max_length=60)
    position: int = 0


# ------------------------------------------------------------------- pieces
class PieceSummary(_ORMModel):
    """List/browse card — the trimmed shape used in grids.

    Carries the piece's images so a grid can render a thumbnail without a
    second request: `image_url` is the primary photo (first image in display
    order) and `images` is every image URL in order. Both are derived from the
    piece's media; build instances with `from_piece()` so the derivation runs.
    """

    id: uuid.UUID
    sku: str
    title: str
    slug: str
    price: Decimal
    currency: str
    condition: PieceCondition
    status: PieceStatus
    size_label: str | None
    house_id: uuid.UUID | None
    universe_id: uuid.UUID | None
    published_at: datetime | None
    image_url: str | None = None       # primary image (first by position), or None
    images: list[str] = []             # all image URLs, in display order

    @classmethod
    def from_piece(cls, piece) -> "PieceSummary":
        """Build a summary from an ORM Piece, deriving the image fields from its
        media (images only, in display order).

        Requires `piece.media` to be loaded — the browse/search/wishlist queries
        eager-load it. If media isn't loaded this degrades to no images rather
        than raising, so it's safe on any Piece.
        """
        obj = cls.model_validate(piece)
        media = getattr(piece, "media", None) or []
        urls = [m.url for m in media if m.media_type is MediaType.IMAGE]
        obj.image_url = urls[0] if urls else None
        obj.images = urls
        return obj


class PieceDetail(PieceSummary):
    """Full piece view — adds description, story and the full media list."""

    description: str | None
    story: str | None
    media: list[MediaOut] = []
    in_wishlist: bool = False   # filled when an authenticated user views it

    @classmethod
    def from_piece(cls, piece) -> "PieceDetail":
        """Build a full detail view, including the image_url/images shortcuts
        (inherited) AND the complete media list."""
        obj = cls.model_validate(piece)   # maps media -> list[MediaOut] too
        media = getattr(piece, "media", None) or []
        urls = [m.url for m in media if m.media_type is MediaType.IMAGE]
        obj.image_url = urls[0] if urls else None
        obj.images = urls
        return obj


class PieceCreate(BaseModel):
    title: TitleText
    sku: str | None = Field(default=None, max_length=64)
    slug: str | None = Field(default=None, max_length=240)
    description: BlurbText | None = None
    story: StoryText | None = None
    house_id: uuid.UUID | None = None
    universe_id: uuid.UUID | None = None
    size_label: str | None = Field(default=None, max_length=32)
    condition: PieceCondition
    price: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="XAF", min_length=3, max_length=3)
    # provenance (usually set when catalogued from a sourcing submission)
    sourcer_id: uuid.UUID | None = None
    acquisition_type: AcquisitionType | None = None
    acquisition_cost: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    consignment_share_percent: Decimal | None = Field(
        default=None, max_digits=5, decimal_places=2
    )


class PieceUpdate(BaseModel):
    title: TitleText | None = None
    description: BlurbText | None = None
    story: StoryText | None = None
    house_id: uuid.UUID | None = None
    universe_id: uuid.UUID | None = None
    size_label: str | None = Field(default=None, max_length=32)
    condition: PieceCondition | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)


# ------------------------------------------------------- publication batches
class PublicationBatchOut(_ORMModel):
    id: uuid.UUID
    label: str
    published_at: datetime | None
    created_at: datetime


class PublicationBatchCreate(BaseModel):
    label: str = Field(min_length=1, max_length=140)
    piece_ids: list[uuid.UUID] = Field(min_length=1)


# ---------------------------------------------------------------- pagination
class PiecesPage(BaseModel):
    items: list[PieceSummary]
    total: int
    limit: int
    offset: int
