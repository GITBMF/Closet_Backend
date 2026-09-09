"""Notification repository — template lookup, branding, and dispatch-log SQL."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.constants import (
    NotificationChannel,
    NotificationStatus,
)
from app.modules.notifications.models import (
    Branding,
    Notification,
    NotificationTemplate,
)

_BRANDING_ID = 1


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------- templates
    async def get_template(
        self, code: str, channel: NotificationChannel, locale: str
    ) -> NotificationTemplate | None:
        stmt = select(NotificationTemplate).where(
            NotificationTemplate.code == code,
            NotificationTemplate.channel == channel,
            NotificationTemplate.locale == locale,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_template_with_fallback(
        self, code: str, channel: NotificationChannel, locale: str, fallback: str
    ) -> NotificationTemplate | None:
        tpl = await self.get_template(code, channel, locale)
        if tpl is None and locale != fallback:
            tpl = await self.get_template(code, channel, fallback)
        return tpl

    async def get_template_by_id(self, template_id: int) -> NotificationTemplate | None:
        return (
            await self.db.execute(
                select(NotificationTemplate).where(
                    NotificationTemplate.id == template_id
                )
            )
        ).scalar_one_or_none()

    async def add_template(self, template: NotificationTemplate) -> NotificationTemplate:
        self.db.add(template)
        await self.db.flush()
        return template

    async def list_templates(
        self, *, code: str | None, channel: NotificationChannel | None
    ) -> list[NotificationTemplate]:
        stmt = select(NotificationTemplate)
        if code is not None:
            stmt = stmt.where(NotificationTemplate.code == code)
        if channel is not None:
            stmt = stmt.where(NotificationTemplate.channel == channel)
        stmt = stmt.order_by(
            NotificationTemplate.code, NotificationTemplate.channel,
            NotificationTemplate.locale,
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # -------------------------------------------------------- branding
    async def get_branding(self) -> Branding | None:
        return (
            await self.db.execute(select(Branding).where(Branding.id == _BRANDING_ID))
        ).scalar_one_or_none()

    def add_branding(self, branding: Branding) -> Branding:
        self.db.add(branding)
        return branding

    # ------------------------------------------------------ dispatch log
    async def add_notification(self, notification: Notification) -> Notification:
        self.db.add(notification)
        await self.db.flush()
        return notification

    async def get_notification(self, notification_id: int) -> Notification | None:
        return (
            await self.db.execute(
                select(Notification).where(Notification.id == notification_id)
            )
        ).scalar_one_or_none()

    async def list_notifications(
        self,
        *,
        status: NotificationStatus | None,
        channel: NotificationChannel | None,
        user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int]:
        base = select(Notification)
        if status is not None:
            base = base.where(Notification.status == status)
        if channel is not None:
            base = base.where(Notification.channel == channel)
        if user_id is not None:
            base = base.where(Notification.recipient_user_id == user_id)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(Notification.queued_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)
