"""Notifier hook — the safe seam other modules use to fire notifications.

WHY THIS EXISTS. Modules like payments and delivery want to notify the customer
from inside a business transaction (a webhook, a status update). But
NotificationService.send() commits its own log row — if it ran on the caller's
session it would commit the caller's half-finished work early, or be rolled back
with it. So the hook runs every notification on a FRESH session, fully isolated
from the caller's transaction.

It also never raises: a messaging problem must never break an order. Any failure
is swallowed here (send() already records it), so callers can fire-and-await
without a try/except.

Callers depend on the small `Notifier` callable, not on NotificationService — so
payments/delivery stay decoupled from notifications' internals and remain trivial
to test (pass a fake notifier, or None).
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.modules.notifications.constants import NotificationChannel

logger = logging.getLogger("closet.notifications")


class Notifier(Protocol):
    async def __call__(
        self,
        code: str,
        *,
        channel: NotificationChannel,
        context: dict | None = None,
        user_id=None,
        to_email: str | None = None,
        to_phone: str | None = None,
        locale: str = "fr",
    ) -> None: ...


async def send_notification(
    code: str,
    *,
    channel: NotificationChannel,
    context: dict | None = None,
    user_id=None,
    to_email: str | None = None,
    to_phone: str | None = None,
    locale: str = "fr",
) -> None:
    """Fire one notification on its own session. Never raises.

    Opens a fresh AsyncSessionLocal so the caller's transaction is untouched.
    Import of AsyncSessionLocal is deferred to keep this module import-light and
    avoid any import cycle with the DB layer.
    """
    try:
        from app.core.database import AsyncSessionLocal
        from app.modules.notifications.dependencies import get_notification_service

        async with AsyncSessionLocal() as db:
            service = get_notification_service(db)
            await service.send(
                code,
                channel=channel,
                context=context,
                user_id=user_id,
                to_email=to_email,
                to_phone=to_phone,
                locale=locale,
            )
    except Exception as exc:  # noqa: BLE001 — notifying must never break a caller
        logger.warning("notification hook failed for %s: %s", code, exc)