"""Integration tests for the notifications module.

The important contract: send() records every attempt as a row and NEVER raises
for a delivery problem (missing template, unresolved recipient, provider error)
— a failed message must not break the caller. These tests assert both the happy
path (render + SENT) and that failures are recorded as FAILED without raising.

Runs against the default console provider, so no messaging credentials are
needed — the same way real sends will be exercised, just with a different
provider behind the same interface.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.modules.notifications.constants import (
    NotificationChannel,
    NotificationStatus,
)
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import TemplateIn
from app.modules.notifications.service import NotificationService


def _svc(db) -> NotificationService:
    return NotificationService(NotificationRepository(db))


async def _seed_template(
    code="order.paid",
    channel=NotificationChannel.WHATSAPP,
    locale="fr",
    body="Bonjour {customer_name}, commande {order_number} payée.",
):
    async with AsyncSessionLocal() as db:
        await _svc(db).create_template(
            TemplateIn(code=code, channel=channel, locale=locale, subject=None, body=body)
        )


@pytest_asyncio.fixture(autouse=True)
async def _clean() -> AsyncGenerator[None, None]:
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE notification, notification_template, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()


class TestSendHappyPath:
    async def test_send_to_explicit_phone_renders_and_sends(self):
        await _seed_template()
        async with AsyncSessionLocal() as db:
            n = await _svc(db).send(
                "order.paid", channel=NotificationChannel.WHATSAPP,
                to_phone="+237600000000",
                context={"customer_name": "Ada", "order_number": "CLO-1"},
            )
        assert n.status is NotificationStatus.SENT
        assert n.recipient_phone == "+237600000000"

    async def test_send_resolves_recipient_from_user(self):
        await _seed_template()
        uid = uuid.uuid4()
        async with AsyncSessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO users (id,email,phone,full_name,role,is_active) "
                    "VALUES (:i,:e,:p,'Bob','customer',true)"
                ),
                {"i": uid, "e": "bob@ex.cm", "p": "+237611111111"},
            )
            await s.commit()
        async with AsyncSessionLocal() as db:
            n = await _svc(db).send(
                "order.paid", channel=NotificationChannel.WHATSAPP, user_id=uid,
                context={"customer_name": "Bob", "order_number": "CLO-2"},
            )
        assert n.status is NotificationStatus.SENT
        assert n.recipient_phone == "+237611111111"

    async def test_locale_fallback_to_default(self):
        await _seed_template(locale="fr")   # only fr exists
        async with AsyncSessionLocal() as db:
            n = await _svc(db).send(
                "order.paid", channel=NotificationChannel.WHATSAPP, locale="en",
                to_phone="+237699999999",
                context={"customer_name": "Cara", "order_number": "CLO-3"},
            )
        assert n.status is NotificationStatus.SENT

    async def test_missing_context_key_renders_placeholder_not_crash(self):
        await _seed_template()
        async with AsyncSessionLocal() as db:
            n = await _svc(db).send(
                "order.paid", channel=NotificationChannel.WHATSAPP,
                to_phone="+237600000000",
                context={"customer_name": "Dee"},   # no order_number
            )
        assert n.status is NotificationStatus.SENT   # placeholder, no crash


class TestSendFailuresNeverRaise:
    async def test_missing_template_records_failed(self):
        async with AsyncSessionLocal() as db:
            n = await _svc(db).send(
                "no.such.template", channel=NotificationChannel.EMAIL,
                to_email="x@y.cm", context={},
            )
        assert n.status is NotificationStatus.FAILED
        assert "no template" in (n.error_message or "")

    async def test_missing_address_records_failed(self):
        await _seed_template()
        async with AsyncSessionLocal() as db:
            n = await _svc(db).send(
                "order.paid", channel=NotificationChannel.WHATSAPP,
                context={"customer_name": "X"},   # no phone anywhere
            )
        assert n.status is NotificationStatus.FAILED
        assert "address" in (n.error_message or "")


class TestTemplates:
    async def test_duplicate_template_rejected(self):
        from app.core.exceptions import ConflictError
        import pytest

        await _seed_template()
        with pytest.raises(ConflictError):
            await _seed_template()   # same (code, channel, locale)

    async def test_dispatch_log_lists_sent_and_failed(self):
        await _seed_template()
        async with AsyncSessionLocal() as db:
            await _svc(db).send(
                "order.paid", channel=NotificationChannel.WHATSAPP,
                to_phone="+237600000000",
                context={"customer_name": "A", "order_number": "CLO-4"},
            )
        async with AsyncSessionLocal() as db:
            await _svc(db).send("nope", channel=NotificationChannel.EMAIL,
                                to_email="a@b.cm", context={})
        async with AsyncSessionLocal() as db:
            items, total = await _svc(db).list_notifications(limit=50, offset=0)
        assert total == 2
        statuses = {i.status for i in items}
        assert NotificationStatus.SENT in statuses
        assert NotificationStatus.FAILED in statuses
