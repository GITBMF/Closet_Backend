"""Notification API contracts (admin template + branding management, dispatch log)."""

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
    html_body: str | None = None   # rich HTML for e-mail; null for WhatsApp/SMS


class TemplateUpdate(BaseModel):
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1)
    html_body: str | None = None   # pass "" to clear, a string to set


class TemplateOut(_ORM):
    id: int
    code: str
    channel: NotificationChannel
    locale: str
    subject: str | None
    body: str
    html_body: str | None


# ----------------------------------------------------------- branding
class BrandingOut(_ORM):
    id: int
    brand_name: str
    logo_url: str | None
    accent_color: str
    support_email: str | None
    footer_note: str | None
    updated_at: datetime


class BrandingUpdate(BaseModel):
    brand_name: str | None = Field(default=None, min_length=1, max_length=120)
    logo_url: str | None = Field(default=None, max_length=1024)
    accent_color: str | None = Field(default=None, min_length=4, max_length=9)
    support_email: str | None = Field(default=None, max_length=255)
    footer_note: str | None = Field(default=None, max_length=300)


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
