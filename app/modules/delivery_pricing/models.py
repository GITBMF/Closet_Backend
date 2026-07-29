"""Delivery-pricing models — the fee table the quote engine reads.

A rate is scoped either to a fixed-rate city or to a region. Rates are
time-bounded (effective_from / effective_to) so a price change is a new row,
never an overwrite — history is preserved.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.delivery_pricing.constants import DeliveryScope

delivery_scope_enum = PGEnum(
    DeliveryScope, name="delivery_scope",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)


class DeliveryRate(Base):
    __tablename__ = "delivery_rate"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[DeliveryScope] = mapped_column(delivery_scope_enum, nullable=False)
    city_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("fixed_rate_city.id", ondelete="CASCADE"), index=True
    )
    region_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("region.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'XAF'"))
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )