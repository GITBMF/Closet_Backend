"""Order models — checkout, line items and status history.

Table is `purchase` (not `order`, which is a SQL reserved word). A purchase
can be placed by a guest (user_id NULL, identified by order_number) or a
logged-in customer. Money is NUMERIC throughout — never float.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.modules.identity.constants import ActorType
from app.modules.orders.constants import OrderStatus

order_status_enum = PGEnum(
    OrderStatus, name="order_status",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)
# ActorType already exists as a PG enum (created by identity's migration);
# reference it without re-creating.
actor_type_enum = PGEnum(
    ActorType, name="actor_type",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)


class Purchase(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "purchase"

    order_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # guest / snapshot contact (also filled for registered users at purchase time)
    customer_name: Mapped[str] = mapped_column(String(150), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[OrderStatus] = mapped_column(
        order_status_enum, nullable=False,
        server_default=OrderStatus.PENDING.value, index=True,
    )

    # address is snapshotted as JSON so a later edit to the saved address does
    # not rewrite history
    delivery_address: Mapped[dict | None] = mapped_column(JSONB)
    delivery_city_id: Mapped[int | None] = mapped_column()
    delivery_region_id: Mapped[int | None] = mapped_column()

    delivery_fee: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'XAF'"))
    quote_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    privilege_code_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("privilege_code.id", ondelete="SET NULL")
    )

    customer_note: Mapped[str | None] = mapped_column(Text)
    admin_note: Mapped[str | None] = mapped_column(Text)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[PurchaseItem]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan"
    )


class PurchaseItem(Base):
    """A line item: one piece in a purchase, with price snapshotted."""

    __tablename__ = "purchase_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("purchase.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    piece_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("piece.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)   # snapshot
    price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)  # snapshot

    purchase: Mapped[Purchase] = relationship(back_populates="items")

    __table_args__ = (
        # a 1-of-1 piece can appear in a purchase at most once
        UniqueConstraint("purchase_id", "piece_id", name="uq_purchase_item"),
    )


class PurchaseStatusHistory(Base):
    """Append-only status timeline for a purchase (disputes, ops)."""

    __tablename__ = "purchase_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("purchase.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    from_status: Mapped[OrderStatus | None] = mapped_column(order_status_enum)
    to_status: Mapped[OrderStatus] = mapped_column(order_status_enum, nullable=False)
    actor_type: Mapped[ActorType] = mapped_column(actor_type_enum, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )