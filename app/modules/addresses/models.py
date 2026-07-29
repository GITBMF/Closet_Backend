"""Address models — a customer's saved delivery addresses.

An address is anchored to the delivery-zone hierarchy (geo) so the pricing
engine can quote a fee. The CHECK enforces exactly one addressing regime:
either a fixed-rate city (+ optional neighbourhood) OR a free region for
out-of-zone delivery, never both.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey


class Address(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "address"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    label: Mapped[str | None] = mapped_column(String(60))
    recipient_name: Mapped[str] = mapped_column(String(150), nullable=False)
    recipient_phone: Mapped[str] = mapped_column(String(32), nullable=False)

    city_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("fixed_rate_city.id", ondelete="RESTRICT"), index=True
    )
    neighbourhood_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("neighbourhood.id", ondelete="SET NULL")
    )
    region_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("region.id", ondelete="RESTRICT")
    )
    division_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("division.id", ondelete="SET NULL")
    )
    subdivision_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("subdivision.id", ondelete="SET NULL")
    )

    details: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (
        CheckConstraint(
            "(city_id IS NOT NULL) <> (region_id IS NOT NULL)",
            name="ck_address_one_regime",
        ),
    )