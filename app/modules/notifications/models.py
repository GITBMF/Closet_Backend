"""Notification models — dispatch log and templates.

notification          : one queued/sent message (any channel)
notification_template : localized message templates keyed by (code, channel, locale)

Other modules never send directly; they call notifications.service.send(...),
which writes a row here and hands off to the channel provider.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.notifications.constants import NotificationChannel, NotificationStatus

notification_channel_enum = PGEnum(
    NotificationChannel, name="notification_channel",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)
notification_status_enum = PGEnum(
    NotificationStatus, name="notification_status",
    values_callable=lambda e: [m.value for m in e], create_type=False,
)


class NotificationTemplate(Base):
    __tablename__ = "notification_template"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(notification_channel_enum, nullable=False)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, server_default=text("'fr'"))
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", "channel", "locale", name="uq_template_code_channel_locale"),
    )


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    recipient_phone: Mapped[str | None] = mapped_column(String(32))
    recipient_email: Mapped[str | None] = mapped_column(String(255))
    channel: Mapped[NotificationChannel] = mapped_column(notification_channel_enum, nullable=False)
    template_code: Mapped[str | None] = mapped_column(String(60))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[NotificationStatus] = mapped_column(
        notification_status_enum, nullable=False,
        server_default=NotificationStatus.QUEUED.value, index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))