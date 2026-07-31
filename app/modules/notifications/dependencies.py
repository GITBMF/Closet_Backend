"""Notification dependencies.

Two ways to get the service:
  * get_notification_service(db) — for other modules that already hold a session
    and call send() as part of their own request (they pass their db in).
  * Service (FastAPI dep) — for this module's own admin routes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import NotificationService


def get_notification_service(db: AsyncSession) -> NotificationService:
    return NotificationService(NotificationRepository(db))


def _service_dep(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationService:
    return get_notification_service(db)


Service = Annotated[NotificationService, Depends(_service_dep)]