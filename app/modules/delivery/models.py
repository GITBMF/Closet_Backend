"""Delivery-execution models — couriers and the courier access link.

courier             : optional named courier account
delivery            : one purchase's delivery, assigned to a courier
delivery_event      : status timeline
courier_access_link : the signed, expiring link a courier uses WITHOUT an
                      account (spec 7.3). Only the token hash is stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.modules.delivery.constants import DeliveryStatus

delivery_status_enum = PGEnum(
    DeliveryStatus, name="delivery_status",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)


class Courier(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "courier"

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Delivery(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "delivery"

    purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("purchase.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    courier_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courier.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        delivery_status_enum, nullable=False,
        server_default=DeliveryStatus.ASSIGNED.value, index=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list[DeliveryEvent]] = relationship(
        back_populates="delivery", cascade="all, delete-orphan"
    )
    links: Mapped[list[CourierAccessLink]] = relationship(
        back_populates="delivery", cascade="all, delete-orphan"
    )


class DeliveryEvent(UUIDPrimaryKey, Base):
    __tablename__ = "delivery_event"

    delivery_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("delivery.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    status: Mapped[DeliveryStatus] = mapped_column(delivery_status_enum, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(40))   # admin | courier_link | system
    link_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("courier_access_link.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    delivery: Mapped[Delivery] = relationship(back_populates="events")


class CourierAccessLink(UUIDPrimaryKey, Base):
    __tablename__ = "courier_access_link"

    delivery_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("delivery.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    delivery: Mapped[Delivery] = relationship(back_populates="links")