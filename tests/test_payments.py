"""Integration tests for the payments module.

Covers the whole payment lifecycle against the fake provider: initiate,
idempotent re-initiate, the signature-checked idempotent webhook (success and
failure), a bad-signature no-op, manual reconcile, and refund. The success and
failure paths assert the cross-module effect on orders (mark_paid sells the
pieces, cancel releases them).

The webhook is driven with FakeProvider-signed bodies so no real provider or
network is involved — the same way CinetPay callbacks will be exercised later,
just with a different signer.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.modules.catalogue.repository import CatalogueRepository
from app.modules.catalogue.service import CatalogueService
from app.modules.delivery_pricing.repository import DeliveryPricingRepository
from app.modules.delivery_pricing.service import DeliveryPricingService
from app.modules.geo.repository import GeoRepository
from app.modules.identity.constants import ActorType
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.modules.payments.constants import PaymentStatus
from app.modules.payments.providers.fake import FakeProvider
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import InitiateIn, ReconcileIn, RefundIn
from app.modules.payments.service import PaymentService


# --------------------------------------------------------------- helpers
def _order_service(db) -> OrderService:
    cat = CatalogueService(CatalogueRepository(db), storage=None)
    pr = DeliveryPricingService(DeliveryPricingRepository(db), GeoRepository(db))
    return OrderService(OrderRepository(db), cat, pr)


def _payment_service(db) -> PaymentService:
    return PaymentService(
        PaymentRepository(db),
        _order_service(db),
        FakeProvider(),
        currency="XAF",
        return_url="https://closet.cm/return",
        notify_url="https://closet.cm/webhook",
    )


async def _seed_pending_order(total: str = "45000.00") -> tuple[uuid.UUID, str, uuid.UUID]:
    """A reserved piece + a pending order holding it (checkout shortcut)."""
    oid, pid = uuid.uuid4(), uuid.uuid4()
    onum = f"CLO-20260731-{uuid.uuid4().hex[:4].upper()}"
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO piece (id,title,slug,price,status,sku,condition,currency) "
                "VALUES (:id,'Silk Dress',:slug,25000,'reserved',:sku,'good','XAF')"
            ),
            {"id": pid, "slug": f"silk-{uuid.uuid4().hex[:6]}",
             "sku": f"CLO-{uuid.uuid4().hex[:6]}"},
        )
        await s.execute(
            text(
                "INSERT INTO purchase (id,order_number,customer_name,customer_phone,"
                "status,subtotal,delivery_fee,total,currency) VALUES "
                "(:id,:onum,'Ada Lovelace','+237600000000','pending',25000,2000,:total,'XAF')"
            ),
            {"id": oid, "onum": onum, "total": total},
        )
        await s.execute(
            text(
                "INSERT INTO purchase_item (purchase_id,piece_id,title,price) "
                "VALUES (:p,:pc,'Silk Dress',25000)"
            ),
            {"p": oid, "pc": pid},
        )
        await s.execute(
            text(
                "INSERT INTO purchase_status_history (purchase_id,to_status,actor_type,reason) "
                "VALUES (:p,'pending','system','order placed')"
            ),
            {"p": oid},
        )
        await s.commit()
    return oid, onum, pid


async def _seed_admin() -> uuid.UUID:
    admin_id = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_active) "
                "VALUES (:i,:e,'Admin','admin',true)"
            ),
            {"i": admin_id, "e": f"admin-{admin_id.hex[:6]}@c.cm"},
        )
        await s.commit()
    return admin_id


def _signed_webhook(status: str, reference: str, event_id: str):
    body = json.dumps(
        {"status": status, "reference": reference, "event_id": event_id}
    ).encode()
    return body, {"x-fake-signature": FakeProvider.sign_body(body)}


async def _piece_status(pid: uuid.UUID) -> str:
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(text("SELECT status FROM piece WHERE id=:i"), {"i": pid})
        ).scalar()


async def _order_status(oid: uuid.UUID) -> str:
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(text("SELECT status FROM purchase WHERE id=:i"), {"i": oid})
        ).scalar()


@pytest_asyncio.fixture(autouse=True)
async def _clean() -> AsyncGenerator[None, None]:
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE refund, payment_event, payment, payment_provider, "
                "purchase_status_history, purchase_item, purchase, piece, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()


# ------------------------------------------------------------------ tests
class TestInitiate:
    async def test_initiate_creates_pending_payment(self):
        _, onum, _ = await _seed_pending_order()
        async with AsyncSessionLocal() as db:
            payment = await _payment_service(db).initiate(InitiateIn(order_number=onum))
        assert payment.status is PaymentStatus.PENDING
        assert payment.amount == Decimal("45000.00")
        assert payment.provider_reference.startswith("FAKE-")
        assert getattr(payment, "_payment_url", None)

    async def test_initiate_is_idempotent(self):
        _, onum, _ = await _seed_pending_order()
        async with AsyncSessionLocal() as db:
            first = await _payment_service(db).initiate(InitiateIn(order_number=onum))
        async with AsyncSessionLocal() as db:
            second = await _payment_service(db).initiate(InitiateIn(order_number=onum))
        assert first.id == second.id  # same attempt, no double charge


class TestWebhook:
    async def test_success_marks_order_paid_and_sells_pieces(self):
        oid, onum, pid = await _seed_pending_order()
        async with AsyncSessionLocal() as db:
            p = await _payment_service(db).initiate(InitiateIn(order_number=onum))
            idem = p.idempotency_key
            pay_id = p.id
        body, headers = _signed_webhook("success", idem, "evt-1")
        async with AsyncSessionLocal() as db:
            await _payment_service(db).handle_webhook(raw_body=body, headers=headers)
        async with AsyncSessionLocal() as db:
            status = (
                await db.execute(text("SELECT status FROM payment WHERE id=:i"), {"i": pay_id})
            ).scalar()
        assert status == "succeeded"
        assert await _order_status(oid) == "paid"
        assert await _piece_status(pid) == "sold"

    async def test_webhook_retry_is_deduped(self):
        _, onum, _ = await _seed_pending_order()
        async with AsyncSessionLocal() as db:
            p = await _payment_service(db).initiate(InitiateIn(order_number=onum))
            idem = p.idempotency_key
        body, headers = _signed_webhook("success", idem, "evt-dup")
        for _ in range(2):
            async with AsyncSessionLocal() as db:
                await _payment_service(db).handle_webhook(raw_body=body, headers=headers)
        async with AsyncSessionLocal() as db:
            count = (
                await db.execute(
                    text("SELECT count(*) FROM payment_event WHERE provider_event_id='evt-dup'")
                )
            ).scalar()
        assert count == 1

    async def test_bad_signature_changes_nothing(self):
        oid, onum, _ = await _seed_pending_order()
        async with AsyncSessionLocal() as db:
            p = await _payment_service(db).initiate(InitiateIn(order_number=onum))
            idem, pay_id = p.idempotency_key, p.id
        body = json.dumps({"status": "success", "reference": idem, "event_id": "evt-bad"}).encode()
        async with AsyncSessionLocal() as db:
            await _payment_service(db).handle_webhook(
                raw_body=body, headers={"x-fake-signature": "WRONG"}
            )
        async with AsyncSessionLocal() as db:
            status = (
                await db.execute(text("SELECT status FROM payment WHERE id=:i"), {"i": pay_id})
            ).scalar()
            sig = (
                await db.execute(
                    text("SELECT signature_valid FROM payment_event WHERE provider_event_id='evt-bad'")
                )
            ).scalar()
        assert status == "pending"
        assert await _order_status(oid) == "pending"
        assert sig is False

    async def test_failure_cancels_order_and_releases_pieces(self):
        oid, onum, pid = await _seed_pending_order()
        async with AsyncSessionLocal() as db:
            p = await _payment_service(db).initiate(InitiateIn(order_number=onum))
            idem, pay_id = p.idempotency_key, p.id
        body, headers = _signed_webhook("failed", idem, "evt-fail")
        async with AsyncSessionLocal() as db:
            await _payment_service(db).handle_webhook(raw_body=body, headers=headers)
        async with AsyncSessionLocal() as db:
            status = (
                await db.execute(text("SELECT status FROM payment WHERE id=:i"), {"i": pay_id})
            ).scalar()
        assert status == "failed"
        assert await _order_status(oid) == "cancelled"
        assert await _piece_status(pid) == "published"   # released back to the shop


class TestReconcile:
    async def test_manual_reconcile_to_succeeded(self):
        oid, onum, pid = await _seed_pending_order()
        admin_id = await _seed_admin()
        async with AsyncSessionLocal() as db:
            p = await _payment_service(db).initiate(InitiateIn(order_number=onum))
            pay_id = p.id
        async with AsyncSessionLocal() as db:
            await _payment_service(db).reconcile(
                pay_id, ReconcileIn(status=PaymentStatus.SUCCEEDED, note="checked"),
                admin_id=admin_id,
            )
        assert await _order_status(oid) == "paid"
        assert await _piece_status(pid) == "sold"


class TestRefund:
    async def test_full_refund_marks_refunded(self):
        _, onum, _ = await _seed_pending_order()
        admin_id = await _seed_admin()
        async with AsyncSessionLocal() as db:
            p = await _payment_service(db).initiate(InitiateIn(order_number=onum))
            idem, pay_id = p.idempotency_key, p.id
        body, headers = _signed_webhook("success", idem, "evt-ok")
        async with AsyncSessionLocal() as db:
            await _payment_service(db).handle_webhook(raw_body=body, headers=headers)
        async with AsyncSessionLocal() as db:
            refund = await _payment_service(db).refund(
                pay_id, RefundIn(amount=Decimal("45000.00"), reason="damaged"),
                admin_id=admin_id,
            )
        assert refund.amount == Decimal("45000.00")
        async with AsyncSessionLocal() as db:
            status = (
                await db.execute(text("SELECT status FROM payment WHERE id=:i"), {"i": pay_id})
            ).scalar()
        assert status == "refunded"

    async def test_refund_exceeding_payment_is_rejected(self):
        from app.core.exceptions import ValidationError
        import pytest

        _, onum, _ = await _seed_pending_order()
        admin_id = await _seed_admin()
        async with AsyncSessionLocal() as db:
            p = await _payment_service(db).initiate(InitiateIn(order_number=onum))
            idem, pay_id = p.idempotency_key, p.id
        body, headers = _signed_webhook("success", idem, "evt-ok2")
        async with AsyncSessionLocal() as db:
            await _payment_service(db).handle_webhook(raw_body=body, headers=headers)
        with pytest.raises(ValidationError):
            async with AsyncSessionLocal() as db:
                await _payment_service(db).refund(
                    pay_id, RefundIn(amount=Decimal("99999.00"), reason="too much"),
                    admin_id=admin_id,
                )