"""Throwaway diagnostic: run ONE happy-path send and print what actually failed.
Run from your repo root with your venv:  python diag_notif.py
It uses your real settings/DB/config — no sandbox assumptions."""
import asyncio, uuid

async def main():
    from app.core.database import AsyncSessionLocal
    from app.modules.notifications.repository import NotificationRepository
    from app.modules.notifications.service import NotificationService
    from app.modules.notifications.schemas import TemplateIn
    from app.modules.notifications.constants import NotificationChannel
    from sqlalchemy import text

    def svc(s): return NotificationService(NotificationRepository(s))

    # clean + seed a template exactly like the test does
    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM notification"))
        await s.execute(text("DELETE FROM notification_template"))
        await s.commit()
    async with AsyncSessionLocal() as s:
        await svc(s).create_template(TemplateIn(
            code="order.paid", channel=NotificationChannel.WHATSAPP, locale="fr",
            subject=None, body="Bonjour {customer_name}, commande {order_number}."))

    # the send that the failing test does
    async with AsyncSessionLocal() as s:
        n = await svc(s).send(
            "order.paid", channel=NotificationChannel.WHATSAPP,
            to_phone="+237600000000",
            context={"customer_name": "Ada", "order_number": "CLO-1"})
        print("STATUS       :", n.status.value)
        print("ERROR_MESSAGE:", repr(n.error_message))

    # also print what the config value actually is on your machine
    from app.core.config import settings
    val = settings.NOTIFICATIONS_PROVIDERS
    print("NOTIFICATIONS_PROVIDERS type :", type(val).__name__)
    print("NOTIFICATIONS_PROVIDERS value:", repr(val))

asyncio.run(main())
