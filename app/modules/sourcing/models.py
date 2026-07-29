"""Sourcing models — the supplier side.

sourcer_profile           : a user's supplier membership (1:1 with users)
submission                : an item offered for sale, before review
submission_media          : photos of a submission
submission_status_history : review timeline
payout                    : money owed to a sourcer
payout_item               : which pieces a payout covers
entrust_request           : deposit-sale (consignment) lifecycle
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
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.modules.identity.constants import ActorType
from app.modules.sourcing.constants import (
    CollaborationType,
    CollectionMethod,
    EntrustStatus,
    PayoutStatus,
    SourcerStatus,
    SubmissionStatus,
)

sourcer_status_enum = PGEnum(SourcerStatus, name="sourcer_status", values_callable=lambda e: [m.value for m in e], create_type=False)
collaboration_type_enum = PGEnum(CollaborationType, name="collaboration_type", values_callable=lambda e: [m.value for m in e], create_type=False)
submission_status_enum = PGEnum(SubmissionStatus, name="submission_status", values_callable=lambda e: [m.value for m in e], create_type=False)
payout_status_enum = PGEnum(PayoutStatus, name="payout_status", values_callable=lambda e: [m.value for m in e], create_type=False)
entrust_status_enum = PGEnum(EntrustStatus, name="entrust_status", values_callable=lambda e: [m.value for m in e], create_type=False)
collection_method_enum = PGEnum(CollectionMethod, name="collection_method", values_callable=lambda e: [m.value for m in e], create_type=False)
actor_type_enum = PGEnum(ActorType, name="actor_type", values_callable=lambda e: [m.value for m in e], create_type=False)


class SourcerProfile(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "sourcer_profile"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[SourcerStatus] = mapped_column(
        sourcer_status_enum, nullable=False,
        server_default=SourcerStatus.PENDING.value, index=True,
    )
    collaboration_type: Mapped[CollaborationType | None] = mapped_column(collaboration_type_enum)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payout_method: Mapped[str | None] = mapped_column(String(40))
    payout_phone: Mapped[str | None] = mapped_column(String(32))
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Submission(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "submission"

    sourcer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sourcer_profile.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    item_type: Mapped[str | None] = mapped_column(String(80))
    brand: Mapped[str | None] = mapped_column(String(120))
    size_label: Mapped[str | None] = mapped_column(String(32))
    condition_claimed: Mapped[str | None] = mapped_column(String(40))
    desired_price: Mapped[float | None] = mapped_column(Numeric(14, 2))
    story: Mapped[str | None] = mapped_column(Text)
    share_permission: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[SubmissionStatus] = mapped_column(
        submission_status_enum, nullable=False,
        server_default=SubmissionStatus.SUBMITTED.value, index=True,
    )
    refusal_reason: Mapped[str | None] = mapped_column(Text)
    collection_method: Mapped[CollectionMethod | None] = mapped_column(collection_method_enum)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    piece_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("piece.id", ondelete="SET NULL")
    )

    media: Mapped[list[SubmissionMedia]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )


class SubmissionMedia(UUIDPrimaryKey, Base):
    __tablename__ = "submission_media"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("submission.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    submission: Mapped[Submission] = relationship(back_populates="media")


class SubmissionStatusHistory(Base):
    __tablename__ = "submission_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("submission.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    from_status: Mapped[SubmissionStatus | None] = mapped_column(submission_status_enum)
    to_status: Mapped[SubmissionStatus] = mapped_column(submission_status_enum, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class Payout(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "payout"

    sourcer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sourcer_profile.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'XAF'"))
    status: Mapped[PayoutStatus] = mapped_column(
        payout_status_enum, nullable=False,
        server_default=PayoutStatus.PENDING.value, index=True,
    )
    method: Mapped[str | None] = mapped_column(String(40))
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[PayoutItem]] = relationship(
        back_populates="payout", cascade="all, delete-orphan"
    )


class PayoutItem(UUIDPrimaryKey, Base):
    __tablename__ = "payout_item"

    payout_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payout.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    piece_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("piece.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    payout: Mapped[Payout] = relationship(back_populates="items")


class EntrustRequest(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "entrust_request"

    piece_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("piece.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    status: Mapped[EntrustStatus] = mapped_column(
        entrust_status_enum, nullable=False,
        server_default=EntrustStatus.REQUESTED.value,
    )
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    handled_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )