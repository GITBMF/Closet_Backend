"""Integration tests for the returns module.

Covers the post-sale flow against real tables: a customer requests to return a
piece from a completed order, ownership and eligibility validation, admin approve
(issues a refund via the payments service), resolve (restocks the piece via the
catalogue service: SOLD -> published), reject (no money/stock movement), the
state machine, and per-user scoping of "my returns".

Payments uses a fake provider (so refund() runs without a real gateway); orders
and catalogue are the real services.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.catalogue.repository import CatalogueRepository
from app.modules.catalogue.service import CatalogueService
from app.modules.delivery_pricing.repository import DeliveryPricingRepository
from app.modules.delivery_pricing.service import DeliveryPricingService
from app.modules.geo.repository import GeoRepository
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.service import PaymentService
from app.modules.returns.constants import ReturnStatus
from app.modules.returns.repository import ReturnsRepository
from app.modules.returns.schemas import ApproveIn, RejectIn, ResolveIn, ReturnCreate
from app.modules.returns.service import ReturnsService


class _FakeRefundResult:
    def __init__(self) -> None:
        self.provider_reference = "rf-" + uuid.uuid4().hex[:8]
        self.raw: dict = {}


class _FakeProvider:
    async def refund(self, *, provider_reference, amount, **kw):
        return _FakeRefundResult()


def _ret_svc(db) -> ReturnsService:
    catalogue = CatalogueService(CatalogueRepository(db), storage=None)
    pricing = DeliveryPricingService(DeliveryPricingRepository(db), GeoRepository(db))
    orders = OrderService(OrderRepository(db), catalogue, pricing)
    payments = PaymentService(
        PaymentRepository(db), orders, _FakeProvider(),
        currency="XAF", return_url="x", notify_url="y",
    )
    return ReturnsService(ReturnsRepository(db), orders, payments, catalogue)


async def _mk_user() -> uuid.UUID:
    uid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_active) "
                "VALUES (:i,:e,'U','customer',true)"
            ),
            {"i": uid, "e": f"u{uid.hex[:6]}@c.cm"},
        )
        await s.commit()
    return uid


async def _delivered_order(user_id, status="completed") -> tuple[uuid.UUID, uuid.UUID]:
    pid, oid = uuid.uuid4(), uuid.uuid4()
    onum = f"CLO-{uuid.uuid4().hex[:6].upper()}"
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO piece (id,title,slug,price,status,sku,condition,currency) "
                "VALUES (:i,'Coat',:sl,50000,'sold',:sk,'good','XAF')"
            ),
            {"i": pid, "sl": f"c-{pid.hex[:6]}", "sk": f"CLO-{pid.hex[:6]}"},
        )
        await s.execute(
            text(
                "INSERT INTO purchase (id,user_id,order_number,customer_name,customer_phone,"
                "status,subtotal,delivery_fee,total,currency) "
                "VALUES (:i,:u,:n,'Ada','+237600000000',:st,50000,2000,52000,'XAF')"
            ),
            {"i": oid, "u": user_id, "n": onum, "st": status},
        )
        await s.execute(
            text(
                "INSERT INTO purchase_item (purchase_id,piece_id,title,price) "
                "VALUES (:p,:pc,'Coat',50000)"
            ),
            {"p": oid, "pc": pid},
        )
        await s.execute(
            text(
                "INSERT INTO payment_provider (id,code,name,is_active) "
                "VALUES (1,'fake','Fake',true) ON CONFLICT DO NOTHING"
            )
        )
        await s.execute(
            text(
                "INSERT INTO payment (id,purchase_id,provider_id,status,amount,currency,"
                "idempotency_key,provider_reference) "
                "VALUES (:i,:pu,1,'succeeded',52000,'XAF',:k,:r)"
            ),
            {"i": uuid.uuid4(), "pu": oid, "k": f"k{oid.hex[:8]}", "r": f"r{oid.hex[:8]}"},
        )
        await s.commit()
    return oid, pid


async def _piece_status(pid) -> str:
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(text("SELECT status FROM piece WHERE id=:i"), {"i": pid})
        ).scalar()


@pytest_asyncio.fixture(autouse=True)
async def _clean() -> AsyncGenerator[None, None]:
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE return_ticket, refund, payment_event, payment, payment_provider, "
                "purchase_item, purchase, piece, users RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()


class TestRequest:
    async def test_request_on_completed_order(self):
        uid = await _mk_user()
        oid, pid = await _delivered_order(uid)
        async with AsyncSessionLocal() as db:
            t = await _ret_svc(db).request_return(
                uid, ReturnCreate(purchase_id=oid, piece_id=pid, reason="too small")
            )
        assert t.status is ReturnStatus.REQUESTED

    async def test_duplicate_open_ticket_rejected(self):
        uid = await _mk_user()
        oid, pid = await _delivered_order(uid)
        async with AsyncSessionLocal() as db:
            await _ret_svc(db).request_return(uid, ReturnCreate(purchase_id=oid, piece_id=pid))
        with pytest.raises(ConflictError):
            async with AsyncSessionLocal() as db:
                await _ret_svc(db).request_return(uid, ReturnCreate(purchase_id=oid, piece_id=pid))

    async def test_other_users_order_hidden(self):
        uid = await _mk_user()
        oid, pid = await _delivered_order(uid)
        other = await _mk_user()
        with pytest.raises(NotFoundError):
            async with AsyncSessionLocal() as db:
                await _ret_svc(db).request_return(other, ReturnCreate(purchase_id=oid, piece_id=pid))

    async def test_piece_not_in_order(self):
        uid = await _mk_user()
        oid, _ = await _delivered_order(uid)
        with pytest.raises(ValidationError):
            async with AsyncSessionLocal() as db:
                await _ret_svc(db).request_return(
                    uid, ReturnCreate(purchase_id=oid, piece_id=uuid.uuid4())
                )

    async def test_non_returnable_order(self):
        uid = await _mk_user()
        oid, pid = await _delivered_order(uid, status="pending")
        with pytest.raises(ConflictError):
            async with AsyncSessionLocal() as db:
                await _ret_svc(db).request_return(uid, ReturnCreate(purchase_id=oid, piece_id=pid))


class TestDecisions:
    async def test_approve_issues_refund_default_line_price(self):
        uid = await _mk_user()
        admin = await _mk_user()
        oid, pid = await _delivered_order(uid)
        async with AsyncSessionLocal() as db:
            t = await _ret_svc(db).request_return(uid, ReturnCreate(purchase_id=oid, piece_id=pid))
            tid = t.id
        async with AsyncSessionLocal() as db:
            t = await _ret_svc(db).approve(tid, ApproveIn(note="ok"), admin_id=admin)
        assert t.status is ReturnStatus.APPROVED
        async with AsyncSessionLocal() as s:
            rows = (
                await s.execute(
                    text(
                        "SELECT amount FROM refund WHERE payment_id IN "
                        "(SELECT id FROM payment WHERE purchase_id=:p)"
                    ),
                    {"p": oid},
                )
            ).fetchall()
        assert len(rows) == 1
        assert Decimal(rows[0][0]) == Decimal("50000.00")

    async def test_resolve_restocks_piece(self):
        uid = await _mk_user()
        admin = await _mk_user()
        oid, pid = await _delivered_order(uid)
        async with AsyncSessionLocal() as db:
            t = await _ret_svc(db).request_return(uid, ReturnCreate(purchase_id=oid, piece_id=pid))
            tid = t.id
            await _ret_svc(db).approve(tid, ApproveIn(), admin_id=admin)
        assert await _piece_status(pid) == "sold"
        async with AsyncSessionLocal() as db:
            t = await _ret_svc(db).resolve(tid, ResolveIn(restock=True), admin_id=admin)
        assert t.status is ReturnStatus.RESOLVED
        assert t.restocked is True
        assert await _piece_status(pid) == "published"

    async def test_cannot_approve_resolved(self):
        uid = await _mk_user()
        admin = await _mk_user()
        oid, pid = await _delivered_order(uid)
        async with AsyncSessionLocal() as db:
            t = await _ret_svc(db).request_return(uid, ReturnCreate(purchase_id=oid, piece_id=pid))
            tid = t.id
            await _ret_svc(db).approve(tid, ApproveIn(), admin_id=admin)
            await _ret_svc(db).resolve(tid, ResolveIn(restock=False), admin_id=admin)
        with pytest.raises(ConflictError):
            async with AsyncSessionLocal() as db:
                await _ret_svc(db).approve(tid, ApproveIn(), admin_id=admin)

    async def test_reject_no_refund_no_restock(self):
        uid = await _mk_user()
        admin = await _mk_user()
        oid, pid = await _delivered_order(uid)
        async with AsyncSessionLocal() as db:
            t = await _ret_svc(db).request_return(uid, ReturnCreate(purchase_id=oid, piece_id=pid))
            tid = t.id
        async with AsyncSessionLocal() as db:
            t = await _ret_svc(db).reject(tid, RejectIn(note="worn beyond policy"), admin_id=admin)
        assert t.status is ReturnStatus.REJECTED
        assert await _piece_status(pid) == "sold"
        async with AsyncSessionLocal() as s:
            n = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM refund WHERE payment_id IN "
                        "(SELECT id FROM payment WHERE purchase_id=:p)"
                    ),
                    {"p": oid},
                )
            ).scalar()
        assert n == 0


class TestScoping:
    async def test_my_returns_scoped_to_user(self):
        uid = await _mk_user()
        oid, pid = await _delivered_order(uid)
        async with AsyncSessionLocal() as db:
            await _ret_svc(db).request_return(uid, ReturnCreate(purchase_id=oid, piece_id=pid))
        other = await _mk_user()
        oid2, pid2 = await _delivered_order(other)
        async with AsyncSessionLocal() as db:
            await _ret_svc(db).request_return(other, ReturnCreate(purchase_id=oid2, piece_id=pid2))
        async with AsyncSessionLocal() as db:
            _, total = await _ret_svc(db).my_returns(uid, limit=50, offset=0)
        assert total == 1
