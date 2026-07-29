"""Showcasing models — sponsors and curated featured slots."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.modules.showcasing.constants import FeaturedSlotType

featured_slot_type_enum = PGEnum(
    FeaturedSlotType, name="featured_slot_type",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)


class Sponsor(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "sponsor"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    link_url: Mapped[str | None] = mapped_column(String(500))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class FeaturedSlot(Base):
    __tablename__ = "featured_slot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slot: Mapped[FeaturedSlotType] = mapped_column(featured_slot_type_enum, nullable=False)
    piece_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("piece.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )