"""Notification API contracts (admin template management + dispatch log)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.notifications.constants import (
    NotificationChannel,
    NotificationStatus,
)


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------- templates
class TemplateIn(BaseModel):
    code: str = Field(min_length=2, max_length=60)
    channel: NotificationChannel
    locale: str = Field(default="fr", min_length=2, max_length=5)
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1)


class TemplateUpdate(BaseModel):
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1)


class TemplateOut(_ORM):
    id: int
    code: str
    channel: NotificationChannel
    locale: str
    subject: str | None
    body: str


# ------------------------------------------------------- dispatch log
class NotificationOut(_ORM):
    id: int
    recipient_user_id: object | None = None
    recipient_phone: str | None
    recipient_email: str | None
    channel: NotificationChannel
    template_code: str | None
    status: NotificationStatus
    error_message: str | None
    queued_at: datetime
    sent_at: datetime | None


class NotificationsPage(BaseModel):
    items: list[NotificationOut]
    total: int
    limit: int
    offset: int