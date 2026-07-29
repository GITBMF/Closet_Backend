"""Catalogue models — the sellable inventory.

house / universe          : controlled vocabularies pieces are tagged with
piece                     : a single 1-of-1 second-hand article
piece_media               : ordered photos/video for a piece
publication_batch         : a group of pieces published together
wishlist_item             : a customer's saved pieces (composite PK)

A `piece` is the heart of the system: it moves draft -> published -> reserved
-> sold. The reservation columns let orders hold a piece for a few minutes at
checkout without a second table.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, TSVECTOR
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDelete, Timestamped, UUIDPrimaryKey
from app.modules.catalogue.constants import (
    AcquisitionType,
    MediaType,
    PieceCondition,
    PieceStatus,
)

piece_status_enum = PGEnum(
    PieceStatus, name="piece_status",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)
piece_condition_enum = PGEnum(
    PieceCondition, name="piece_condition",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)
acquisition_type_enum = PGEnum(
    AcquisitionType, name="acquisition_type",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)
media_type_enum = PGEnum(
    MediaType, name="media_type",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)


class House(UUIDPrimaryKey, Base):
    """A brand/label (e.g. Zara, Nike). Controlled vocabulary."""

    __tablename__ = "house"

    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))


class Universe(UUIDPrimaryKey, Base):
    """A top-level category (e.g. Clothing, Shoes, Home). Controlled."""

    __tablename__ = "universe"

    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))


class Piece(UUIDPrimaryKey, Timestamped, SoftDelete, Base):
    """A single second-hand article for sale (1-of-1)."""

    __tablename__ = "piece"

    sku: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    story: Mapped[str | None] = mapped_column(Text)

    house_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("house.id", ondelete="SET NULL"), index=True
    )
    universe_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("universe.id", ondelete="SET NULL"), index=True
    )

    size_label: Mapped[str | None] = mapped_column(String(32))
    condition: Mapped[PieceCondition] = mapped_column(piece_condition_enum, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'XAF'"))

    status: Mapped[PieceStatus] = mapped_column(
        piece_status_enum, nullable=False,
        server_default=PieceStatus.DRAFT.value, index=True,
    )

    # reservation: orders holds a piece for a few minutes at checkout
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reserved_by_order_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))

    # provenance (sourcing)
    sourcer_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    acquisition_type: Mapped[AcquisitionType | None] = mapped_column(acquisition_type_enum)
    acquisition_cost: Mapped[float | None] = mapped_column(Numeric(14, 2))
    consignment_share_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))

    publication_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publication_batch.id", ondelete="SET NULL"),
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)

    media: Mapped[list[PieceMedia]] = relationship(
        back_populates="piece", cascade="all, delete-orphan",
        order_by="PieceMedia.position",
    )


class PieceMedia(UUIDPrimaryKey, Base):
    """A photo or video attached to a piece, in display order."""

    __tablename__ = "piece_media"

    piece_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("piece.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    media_type: Mapped[MediaType] = mapped_column(
        media_type_enum, nullable=False, server_default=MediaType.IMAGE.value
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    view_label: Mapped[str | None] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    piece: Mapped[Piece] = relationship(back_populates="media")


class PublicationBatch(UUIDPrimaryKey, Base):
    """A named group of pieces published together (a 'drop')."""

    __tablename__ = "publication_batch"

    label: Mapped[str] = mapped_column(String(140), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class WishlistItem(Base):
    """A customer's saved piece. Composite PK (user, piece)."""

    __tablename__ = "wishlist_item"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    piece_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("piece.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )