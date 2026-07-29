"""Privilege-code models — promo / discount codes and their redemptions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.modules.privileges.constants import PrivilegeType

privilege_type_enum = PGEnum(
    PrivilegeType, name="privilege_type",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)


class PrivilegeCode(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "privilege_code"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    type: Mapped[PrivilegeType] = mapped_column(privilege_type_enum, nullable=False)
    value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    min_order_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    max_uses: Mapped[int | None] = mapped_column(Integer)
    times_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class PrivilegeRedemption(UUIDPrimaryKey, Base):
    __tablename__ = "privilege_redemption"

    code_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("privilege_code.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("purchase.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("code_id", "purchase_id", name="uq_redemption_code_purchase"),
    )