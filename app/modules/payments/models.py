"""Payment models — provider-agnostic (CinetPay first).

payment_provider : configured aggregators (CinetPay, later direct MTN/OM)
payment          : one payment attempt against a purchase
payment_event    : raw provider callbacks, for audit & idempotency
refund           : money returned to the customer

Money is NUMERIC. Provider webhooks are recorded verbatim in payment_event
with a unique provider_event_id so a retried callback is processed once.
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
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.modules.payments.constants import PaymentStatus

payment_status_enum = PGEnum(
    PaymentStatus, name="payment_status",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)


class PaymentProvider(Base):
    __tablename__ = "payment_provider"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    config: Mapped[dict | None] = mapped_column(JSONB)   # non-secret settings only


class Payment(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "payment"

    purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("purchase.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    provider_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("payment_provider.id", ondelete="RESTRICT"), nullable=False
    )
    operator: Mapped[str | None] = mapped_column(String(40))   # mtn_momo, orange_money…
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'XAF'"))
    status: Mapped[PaymentStatus] = mapped_column(
        payment_status_enum, nullable=False,
        server_default=PaymentStatus.INITIATED.value, index=True,
    )
    provider_reference: Mapped[str | None] = mapped_column(String(120), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    payer_phone: Mapped[str | None] = mapped_column(String(32))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list[PaymentEvent]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentEvent(Base):
    __tablename__ = "payment_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payment.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    provider_event_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    event_type: Mapped[str | None] = mapped_column(String(60))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    signature_valid: Mapped[bool | None] = mapped_column(Boolean)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    processing_error: Mapped[str | None] = mapped_column(Text)

    payment: Mapped[Payment] = relationship(back_populates="events")


class Refund(UUIDPrimaryKey, Base):
    __tablename__ = "refund"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payment.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )