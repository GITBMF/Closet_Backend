"""Integration tests for the orders module.

Covers checkout (atomic piece reservation + totals), the concurrency guard
(a reserved 1-of-1 can't be bought twice), delivery-quote integration, the
status machine, cancel-releases-pieces, the quote_required manual-fee path,
the payment hooks (mark_paid sells pieces), and access control.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.main import create_app
from app.modules.catalogue.repository import CatalogueRepository
from app.modules.catalogue.service import CatalogueService
from app.modules.delivery_pricing.repository import DeliveryPricingRepository
from app.modules.delivery_pricing.service import DeliveryPricingService
from app.modules.geo.repository import GeoRepository
from app.modules.identity.constants import ActorType
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService

API = "/api/v1"


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _seed() -> AsyncGenerator[None, None]:
    async with AsyncSessionLocal() as s:
        await s.execute(text("INSERT INTO region (name, code) VALUES ('Centre','CE')"))
        await s.execute(
            text(
                "INSERT INTO fixed_rate_city (name, region_id, is_active) "
                "VALUES ('Yaoundé',1,true), ('Maroua',1,true)"
            )
        )
        await s.commit()
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE purchase, purchase_item, purchase_status_history, piece, "
                "piece_media, house, universe, delivery_rate, region, division, "
                "subdivision, fixed_rate_city, neighbourhood, audit_logs, "
                "refresh_tokens, device_tokens, password_reset_tokens, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _admin_token(client: AsyncClient) -> str:
    await client.post(
        f"{API}/auth/register",
        json={"email": "boss@c.cm", "password": "Dressing2026", "full_name": "Boss Lady"},
    )
    async with AsyncSessionLocal() as s:
        await s.execute(text("UPDATE users SET role='admin' WHERE email='boss@c.cm'"))
        await s.commit()
    r = await client.post(
        f"{API}/auth/login", json={"email": "boss@c.cm", "password": "Dressing2026"}
    )
    return r.json()["access_token"]


async def _customer_token(client: AsyncClient, email: str = "cust@c.cm") -> str:
    await client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Dressing2026", "full_name": "Cust Omer"},
    )
    r = await client.post(
        f"{API}/auth/login", json={"email": email, "password": "Dressing2026"}
    )
    return r.json()["access_token"]


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


async def _rate(client: AsyncClient, tok: str, city_id: int, amount: int) -> None:
    await client.post(
        f"{API}/admin/delivery/rates",
        headers=_auth(tok),
        json={"scope": "city", "city_id": city_id, "amount": amount},
    )


async def _published_piece(client: AsyncClient, tok: str, **over) -> str:
    body = {"title": "Silk Dress", "condition": "very_good", "price": 25000}
    body.update(over)
    pid = (await client.post(f"{API}/admin/pieces", headers=_auth(tok), json=body)).json()["id"]
    await client.post(f"{API}/admin/pieces/{pid}/publish", headers=_auth(tok))
    return pid


def _order_service(db) -> OrderService:
    cat = CatalogueService(CatalogueRepository(db))
    pr = DeliveryPricingService(DeliveryPricingRepository(db), GeoRepository(db))
    return OrderService(OrderRepository(db), cat, pr)


async def _piece_status(pid: str) -> str:
    async with AsyncSessionLocal() as db:
        return (await CatalogueRepository(db).get_piece(uuid.UUID(pid))).status.value


class TestCheckout:
    async def test_checkout_reserves_and_totals(self, client: AsyncClient):
        tok = await _admin_token(client)
        await _rate(client, tok, 1, 2000)
        p1 = await _published_piece(client, tok, title="Dress", price=25000)
        p2 = await _published_piece(client, tok, title="Bag", price=18000)
        r = await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p1, p2],
                "customer_name": "Ada Lovelace",
                "customer_phone": "+237600000000",
                "address": {"line1": "Rue 123", "city_id": 1},
            },
        )
        assert r.status_code == 201, r.text
        o = r.json()
        assert o["status"] == "pending"
        assert o["subtotal"] == "43000.00"
        assert o["delivery_fee"] == "2000.00"
        assert o["total"] == "45000.00"
        assert len(o["items"]) == 2
        assert await _piece_status(p1) == "reserved"
        assert await _piece_status(p2) == "reserved"

    async def test_cannot_buy_a_reserved_piece(self, client: AsyncClient):
        tok = await _admin_token(client)
        await _rate(client, tok, 1, 2000)
        p = await _published_piece(client, tok)
        base = {
            "customer_name": "Buyer One",
            "customer_phone": "+237600000000",
            "address": {"line1": "A", "city_id": 1},
        }
        first = await client.post(f"{API}/orders", json={**base, "piece_ids": [p]})
        assert first.status_code == 201
        second = await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Buyer Two",
                "customer_phone": "+237611111111",
                "address": {"line1": "B", "city_id": 1},
            },
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "piece_unavailable"

    async def test_unknown_piece_is_404(self, client: AsyncClient):
        r = await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [str(uuid.uuid4())],
                "customer_name": "Nobody Here",
                "customer_phone": "+237600000000",
                "address": {"line1": "A", "city_id": 1},
            },
        )
        assert r.status_code == 404

    async def test_out_of_zone_is_quote_required(self, client: AsyncClient):
        tok = await _admin_token(client)
        # city 2 (Maroua) has no rate
        p = await _published_piece(client, tok, price=5000)
        r = await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Quentin Blake",
                "customer_phone": "+237600000000",
                "address": {"line1": "W", "city_id": 2},
            },
        )
        o = r.json()
        assert o["status"] == "quote_required"
        assert o["quote_required"] is True
        assert o["total"] == "5000.00"   # subtotal only, fee pending


class TestTracking:
    async def test_track_by_number_is_public(self, client: AsyncClient):
        tok = await _admin_token(client)
        await _rate(client, tok, 1, 2000)
        p = await _published_piece(client, tok)
        o = (await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Grace Hopper",
                "customer_phone": "+237600000000",
                "address": {"line1": "A", "city_id": 1},
            },
        )).json()
        tr = await client.get(f"{API}/orders/{o['order_number']}")
        assert tr.status_code == 200
        assert tr.json()["order_number"] == o["order_number"]

    async def test_unknown_number_is_404(self, client: AsyncClient):
        r = await client.get(f"{API}/orders/CLO-19700101-FFFF")
        assert r.status_code == 404


class TestStatusMachine:
    async def test_admin_advances_status(self, client: AsyncClient):
        tok = await _admin_token(client)
        await _rate(client, tok, 1, 2000)
        p = await _published_piece(client, tok)
        o = (await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Grace Hopper",
                "customer_phone": "+237600000000",
                "address": {"line1": "A", "city_id": 1},
            },
        )).json()
        oid = o["id"]
        # mark paid via the service hook (payments module will call this)
        async with AsyncSessionLocal() as db:
            await _order_service(db).mark_paid(uuid.UUID(oid))
        assert await _piece_status(p) == "sold"
        for target in ("preparing", "ready", "delivering", "completed"):
            r = await client.patch(
                f"{API}/admin/orders/{oid}/status",
                headers=_auth(tok),
                json={"status": target},
            )
            assert r.status_code == 200
            assert r.json()["status"] == target

    async def test_illegal_transition_is_409(self, client: AsyncClient):
        tok = await _admin_token(client)
        await _rate(client, tok, 1, 2000)
        p = await _published_piece(client, tok)
        o = (await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Grace Hopper",
                "customer_phone": "+237600000000",
                "address": {"line1": "A", "city_id": 1},
            },
        )).json()
        # pending -> ready is not allowed (must pass through paid/preparing)
        r = await client.patch(
            f"{API}/admin/orders/{o['id']}/status",
            headers=_auth(tok),
            json={"status": "ready"},
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "invalid_transition"

    async def test_cancel_releases_pieces(self, client: AsyncClient):
        tok = await _admin_token(client)
        await _rate(client, tok, 1, 2000)
        p = await _published_piece(client, tok)
        o = (await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Grace Hopper",
                "customer_phone": "+237600000000",
                "address": {"line1": "A", "city_id": 1},
            },
        )).json()
        assert await _piece_status(p) == "reserved"
        r = await client.patch(
            f"{API}/admin/orders/{o['id']}/status",
            headers=_auth(tok),
            json={"status": "cancelled", "reason": "changed mind"},
        )
        assert r.status_code == 200
        assert await _piece_status(p) == "published"   # released back to the shop


class TestManualQuote:
    async def test_set_fee_moves_to_pending(self, client: AsyncClient):
        tok = await _admin_token(client)
        p = await _published_piece(client, tok, price=5000)
        o = (await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Quentin Blake",
                "customer_phone": "+237600000000",
                "address": {"line1": "W", "city_id": 2},
            },
        )).json()
        assert o["status"] == "quote_required"
        r = await client.post(
            f"{API}/admin/orders/{o['id']}/quote",
            headers=_auth(tok),
            json={"delivery_fee": 4500},
        )
        b = r.json()
        assert b["status"] == "pending"
        assert b["delivery_fee"] == "4500.00"
        assert b["total"] == "9500.00"


class TestPaymentHooks:
    async def test_cancel_hook_releases(self, client: AsyncClient):
        tok = await _admin_token(client)
        await _rate(client, tok, 1, 2000)
        p = await _published_piece(client, tok)
        o = (await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Grace Hopper",
                "customer_phone": "+237600000000",
                "address": {"line1": "A", "city_id": 1},
            },
        )).json()
        async with AsyncSessionLocal() as db:
            await _order_service(db).cancel(
                uuid.UUID(o["id"]), reason="payment failed", actor_type=ActorType.SYSTEM
            )
        assert await _piece_status(p) == "published"


class TestStatusHistory:
    async def test_history_records_the_timeline(self, client: AsyncClient):
        tok = await _admin_token(client)
        await _rate(client, tok, 1, 2000)
        p = await _published_piece(client, tok)
        o = (await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Ada Lovelace",
                "customer_phone": "+237600000000",
                "address": {"line1": "A", "city_id": 1},
            },
        )).json()
        oid = o["id"]
        async with AsyncSessionLocal() as db:
            await _order_service(db).mark_paid(uuid.UUID(oid))
        await client.patch(
            f"{API}/admin/orders/{oid}/status",
            headers=_auth(tok),
            json={"status": "preparing", "reason": "packing"},
        )
        r = await client.get(f"{API}/admin/orders/{oid}/history", headers=_auth(tok))
        assert r.status_code == 200
        entries = r.json()
        assert len(entries) == 3   # placed, paid, preparing
        assert entries[0]["from_status"] is None
        assert entries[0]["to_status"] == "pending"
        assert entries[1]["to_status"] == "paid"
        assert entries[2]["to_status"] == "preparing"
        assert entries[2]["reason"] == "packing"

    async def test_history_unknown_order_is_404(self, client: AsyncClient):
        tok = await _admin_token(client)
        r = await client.get(
            f"{API}/admin/orders/{uuid.uuid4()}/history", headers=_auth(tok)
        )
        assert r.status_code == 404

    async def test_customer_cannot_read_history(self, client: AsyncClient):
        atok = await _admin_token(client)
        await _rate(client, atok, 1, 2000)
        p = await _published_piece(client, atok)
        o = (await client.post(
            f"{API}/orders",
            json={
                "piece_ids": [p],
                "customer_name": "Ada Lovelace",
                "customer_phone": "+237600000000",
                "address": {"line1": "A", "city_id": 1},
            },
        )).json()
        ctok = await _customer_token(client)
        r = await client.get(
            f"{API}/admin/orders/{o['id']}/history", headers=_auth(ctok)
        )
        assert r.status_code == 403


class TestAccessControl:
    async def test_my_orders_needs_auth(self, client: AsyncClient):
        r = await client.get(f"{API}/orders")
        assert r.status_code == 401

    async def test_customer_cannot_list_all(self, client: AsyncClient):
        tok = await _customer_token(client)
        r = await client.get(f"{API}/admin/orders", headers=_auth(tok))
        assert r.status_code == 403

    async def test_customer_sees_own_orders(self, client: AsyncClient):
        atok = await _admin_token(client)
        await _rate(client, atok, 1, 2000)
        p = await _published_piece(client, atok)
        ctok = await _customer_token(client)
        await client.post(
            f"{API}/orders",
            headers=_auth(ctok),
            json={
                "piece_ids": [p],
                "customer_name": "Cust Omer",
                "customer_phone": "+237600000000",
                "address": {"line1": "A", "city_id": 1},
            },
        )
        mine = await client.get(f"{API}/orders", headers=_auth(ctok))
        assert mine.status_code == 200
        assert mine.json()["total"] == 1