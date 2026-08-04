"""Showcasing models — the curated storefront surface.

sponsor        : time-bounded partner banners, ordered by `position`
featured_slot  : ties a catalogue piece to a curated slot for a time window

These map the tables already created in migration 0003 (schema-foundation).
They are read-decorators over the catalogue: showcasing never owns pieces, it
only points at them.
"""

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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.showcasing.constants import FeaturedSlotType


class Sponsor(Base):
    """A partner/brand banner shown on the storefront for a time window."""

    __tablename__ = "sponsor"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    link_url: Mapped[str | None] = mapped_column(String(500))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FeaturedSlot(Base):
    """A curated slot pinning one catalogue piece for a time window."""

    __tablename__ = "featured_slot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slot: Mapped[FeaturedSlotType] = mapped_column(
        PGEnum(
            FeaturedSlotType,
            name="featured_slot_type",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    piece_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("piece.id", ondelete="CASCADE"),
        nullable=False,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )