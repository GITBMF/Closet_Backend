"""Integration tests for the delivery module.

Covers the courier lifecycle against real tables: create (order must be READY),
the signed courier link (raw token issued once, only the hash stored), the
account-less courier view and status updates, the order tracking delivery
progress (READY -> DELIVERING -> COMPLETED), the event timeline, and the link
security checks (invalid / expired / exhausted).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.exceptions import ConflictError, PermissionDeniedError
from app.modules.catalogue.repository import CatalogueRepository
from app.modules.catalogue.service import CatalogueService
from app.modules.delivery.constants import DeliveryStatus
from app.modules.delivery.dependencies import get_delivery_service
from app.modules.delivery.repository import DeliveryRepository
from app.modules.delivery.schemas import (
    AssignIn,
    CourierIn,
    CourierStatusIn,
    CreateDeliveryIn,
    LinkIn,
)
from app.modules.delivery.service import DeliveryService
from app.modules.delivery_pricing.repository import DeliveryPricingRepository
from app.modules.delivery_pricing.service import DeliveryPricingService
from app.modules.geo.repository import GeoRepository
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService


def _svc(db) -> DeliveryService:
    cat = CatalogueService(CatalogueRepository(db), storage=None)
    pr = DeliveryPricingService(DeliveryPricingRepository(db), GeoRepository(db))
    orders = OrderService(OrderRepository(db), cat, pr)
    return DeliveryService(DeliveryRepository(db), orders)


async def _seed_ready_order() -> tuple[uuid.UUID, str]:
    oid = uuid.uuid4()
    onum = f"CLO-20260731-{uuid.uuid4().hex[:4].upper()}"
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO purchase (id,order_number,customer_name,customer_phone,"
                "status,subtotal,delivery_fee,total,currency,delivery_address) VALUES "
                "(:id,:onum,'Ada','+237600000000','ready',25000,2000,27000,'XAF',:addr)"
            ),
            {"id": oid, "onum": onum, "addr": '{"city":"Yaounde"}'},
        )
        await s.execute(
            text(
                "INSERT INTO purchase_status_history (purchase_id,to_status,actor_type,reason) "
                "VALUES (:p,'ready','admin','prepared')"
            ),
            {"p": oid},
        )
        await s.commit()
    return oid, onum


async def _make_courier() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        c = await _svc(db).create_courier(CourierIn(full_name="Jean C", phone="+237699999999"))
        return c.id


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
                "TRUNCATE courier_access_link, delivery_event, delivery, courier, "
                "purchase_status_history, purchase_item, purchase RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()


class TestCreateAssign:
    async def test_create_delivery_for_ready_order(self):
        _, onum = await _seed_ready_order()
        cid = await _make_courier()
        async with AsyncSessionLocal() as db:
            d = await _svc(db).create_delivery(CreateDeliveryIn(order_number=onum, courier_id=cid))
        assert d.status is DeliveryStatus.ASSIGNED
        assert d.courier_id == cid

    async def test_cannot_create_for_non_ready_order(self):
        oid = uuid.uuid4()
        onum = f"CLO-20260731-{uuid.uuid4().hex[:4].upper()}"
        async with AsyncSessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO purchase (id,order_number,customer_name,customer_phone,"
                    "status,subtotal,delivery_fee,total,currency) VALUES "
                    "(:i,:n,'X','+237600000001','pending',1000,0,1000,'XAF')"
                ),
                {"i": oid, "n": onum},
            )
            await s.commit()
        with pytest.raises(ConflictError):
            async with AsyncSessionLocal() as db:
                await _svc(db).create_delivery(CreateDeliveryIn(order_number=onum))

    async def test_cannot_double_create(self):
        _, onum = await _seed_ready_order()
        async with AsyncSessionLocal() as db:
            await _svc(db).create_delivery(CreateDeliveryIn(order_number=onum))
        with pytest.raises(ConflictError):
            async with AsyncSessionLocal() as db:
                await _svc(db).create_delivery(CreateDeliveryIn(order_number=onum))


class TestCourierLinkLifecycle:
    async def test_full_lifecycle_tracks_order(self):
        oid, onum = await _seed_ready_order()
        cid = await _make_courier()
        async with AsyncSessionLocal() as db:
            d = await _svc(db).create_delivery(CreateDeliveryIn(order_number=onum, courier_id=cid))
            did = d.id
        async with AsyncSessionLocal() as db:
            _, token = await _svc(db).generate_link(did, LinkIn(ttl_hours=24, max_uses=10))

        # courier can see it without an account
        async with AsyncSessionLocal() as db:
            view = await _svc(db).courier_view(token)
        assert view.order_number == onum

        # drive picked_up -> in_transit -> delivered; order tracks along
        expected = {
            "picked_up": "delivering",
            "in_transit": "delivering",
            "delivered": "completed",
        }
        for st, exp in expected.items():
            async with AsyncSessionLocal() as db:
                await _svc(db).courier_update_status(
                    token, CourierStatusIn(status=DeliveryStatus(st))
                )
            assert await _order_status(oid) == exp

        # timeline recorded
        async with AsyncSessionLocal() as db:
            events = await _svc(db).events(did)
        assert [e.status.value for e in events] == [
            "assigned", "picked_up", "in_transit", "delivered",
        ]


class TestLinkSecurity:
    async def test_invalid_token_refused(self):
        with pytest.raises(PermissionDeniedError):
            async with AsyncSessionLocal() as db:
                await _svc(db).courier_view("bogus-token")

    async def test_expired_link_refused(self):
        _, onum = await _seed_ready_order()
        async with AsyncSessionLocal() as db:
            d = await _svc(db).create_delivery(CreateDeliveryIn(order_number=onum))
            link, token = await _svc(db).generate_link(d.id, LinkIn(ttl_hours=1, max_uses=5))
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("UPDATE courier_access_link SET expires_at=:e WHERE id=:i"),
                {"e": datetime.now(UTC) - timedelta(hours=1), "i": link.id},
            )
            await s.commit()
        with pytest.raises(PermissionDeniedError):
            async with AsyncSessionLocal() as db:
                await _svc(db).courier_view(token)

    async def test_exhausted_link_refused(self):
        _, onum = await _seed_ready_order()
        async with AsyncSessionLocal() as db:
            d = await _svc(db).create_delivery(CreateDeliveryIn(order_number=onum))
            _, token = await _svc(db).generate_link(d.id, LinkIn(ttl_hours=24, max_uses=1))
        # first use consumes the only allowance (this call still succeeds)
        async with AsyncSessionLocal() as db:
            await _svc(db).courier_update_status(
                token, CourierStatusIn(status=DeliveryStatus.PICKED_UP)
            )
        # second use is refused
        with pytest.raises(PermissionDeniedError):
            async with AsyncSessionLocal() as db:
                await _svc(db).courier_update_status(
                    token, CourierStatusIn(status=DeliveryStatus.IN_TRANSIT)
                )


class TestReassign:
    async def test_reassign_failed_delivery_revives_it(self):
        _, onum = await _seed_ready_order()
        cid = await _make_courier()
        async with AsyncSessionLocal() as db:
            d = await _svc(db).create_delivery(CreateDeliveryIn(order_number=onum, courier_id=cid))
            did = d.id
            _, token = await _svc(db).generate_link(did, LinkIn(ttl_hours=24, max_uses=10))
        async with AsyncSessionLocal() as db:
            await _svc(db).courier_update_status(
                token, CourierStatusIn(status=DeliveryStatus.FAILED, reason="no answer")
            )
        cid2 = await _make_courier()
        async with AsyncSessionLocal() as db:
            d2 = await _svc(db).assign(did, AssignIn(courier_id=cid2))
        assert d2.status is DeliveryStatus.ASSIGNED
        assert d2.courier_id == cid2
