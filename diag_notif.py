"""Deeper notifications diagnostic — prints the FULL traceback that send()
swallowed, plus the resolved provider and config. Run from repo root:

    python diag_notif2.py

Unlike the pytest output (which only shows status=FAILED), this reveals the
actual exception and which provider is being used, so we can see the true cause.
"""
import asyncio
import traceback


async def main():
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal
    from app.core.config import settings
    from app.modules.notifications.repository import NotificationRepository
    from app.modules.notifications.service import NotificationService
    from app.modules.notifications.schemas import TemplateIn
    from app.modules.notifications.constants import NotificationChannel
    from app.modules.notifications.providers.registry import get_provider, _provider_mapping

    # 1. What provider is actually selected for WhatsApp?
    print("=== config / provider ===")
    val = settings.NOTIFICATIONS_PROVIDERS
    print("NOTIFICATIONS_PROVIDERS type :", type(val).__name__)
    print("NOTIFICATIONS_PROVIDERS value:", repr(val))
    try:
        print("normalised mapping           :", _provider_mapping())
    except Exception as e:
        print("mapping error                :", repr(e))
    prov = get_provider(NotificationChannel.WHATSAPP)
    print("provider for whatsapp        :", type(prov).__name__, "code=", getattr(prov, "code", "?"))

    # 2. Seed a template exactly like the test.
    def svc(s):
        return NotificationService(NotificationRepository(s))

    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM notification"))
        await s.execute(text("DELETE FROM notification_template"))
        await s.commit()
    async with AsyncSessionLocal() as s:
        await svc(s).create_template(TemplateIn(
            code="order.paid", channel=NotificationChannel.WHATSAPP, locale="fr",
            subject=None, body="Bonjour {customer_name}, commande {order_number}."))

    # 3. Manually replay send()'s body WITHOUT the try/except, so any exception
    #    shows its full traceback instead of being hidden as status=FAILED.
    print("\n=== replaying send() body with full traceback on error ===")
    from app.modules.notifications.models import Notification
    from app.modules.notifications.constants import NotificationStatus
    from app.modules.notifications.service import _render

    async with AsyncSessionLocal() as s:
        service = svc(s)
        try:
            template = await service.repo.get_template_with_fallback(
                "order.paid", NotificationChannel.WHATSAPP, "fr", "fr")
            print("template found:", template is not None)
            to = service._address_for(NotificationChannel.WHATSAPP, None, "+237600000000")
            print("address:", to)
            body = _render(template.body, {"customer_name": "Ada", "order_number": "CLO-1"})
            print("rendered body:", body)
            provider = get_provider(NotificationChannel.WHATSAPP)
            result = await provider.send_message(to=to, subject=None, body=body)
            print("provider result: ok=", result.ok, "error=", result.error)

            n = Notification(
                recipient_phone="+237600000000",
                channel=NotificationChannel.WHATSAPP,
                template_code="order.paid",
                payload={"customer_name": "Ada"},
                status=NotificationStatus.SENT if result.ok else NotificationStatus.FAILED,
            )
            s.add(n)
            await s.commit()
            print("COMMIT OK — row id:", n.id, "status:", n.status.value)
        except Exception:
            print("!!! THIS is what send() was hiding as status=FAILED:")
            traceback.print_exc()

    # 4. Also run the real send() and print its stored error_message.
    print("\n=== real send() outcome ===")
    async with AsyncSessionLocal() as s:
        n = await svc(s).send(
            "order.paid", channel=NotificationChannel.WHATSAPP,
            to_phone="+237600000000",
            context={"customer_name": "Ada", "order_number": "CLO-1"})
        print("STATUS       :", n.status.value)
        print("ERROR_MESSAGE:", repr(n.error_message))


asyncio.run(main())