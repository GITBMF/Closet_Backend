"""Integration tests for the delivery-pricing module.

Covers the quote engine's resolution order (city -> region -> quote_required),
rate superseding with history preservation, validation, and the access-control
matrix (quote public, rate writes need DELIVERY_RATE_MANAGE).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.main import create_app

API = "/api/v1"


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _seed() -> AsyncGenerator[None, None]:
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO region (name, code) VALUES ('Centre','CE'), ('Littoral','LT')")
        )
        await s.execute(
            text(
                "INSERT INTO fixed_rate_city (name, region_id, is_active) VALUES "
                "('Yaoundé',1,true), ('Douala',2,true), ('Kribi',2,true)"
            )
        )
        await s.commit()
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE delivery_rate, region, division, subdivision, "
                "fixed_rate_city, neighbourhood, audit_logs, refresh_tokens, "
                "device_tokens, password_reset_tokens, users RESTART IDENTITY CASCADE"
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
        json={"email": "boss@closet.cm", "password": "Dressing2026", "full_name": "Boss"},
    )
    async with AsyncSessionLocal() as s:
        await s.execute(text("UPDATE users SET role='admin' WHERE email='boss@closet.cm'"))
        await s.commit()
    r = await client.post(
        f"{API}/auth/login",
        json={"email": "boss@closet.cm", "password": "Dressing2026"},
    )
    return r.json()["access_token"]


async def _customer_token(client: AsyncClient) -> str:
    await client.post(
        f"{API}/auth/register",
        json={"email": "cust@closet.cm", "password": "Dressing2026", "full_name": "Cust"},
    )
    r = await client.post(
        f"{API}/auth/login",
        json={"email": "cust@closet.cm", "password": "Dressing2026"},
    )
    return r.json()["access_token"]


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


class TestQuoteEngine:
    async def test_no_rate_is_quote_required(self, client: AsyncClient):
        r = await client.get(f"{API}/delivery/quote?city_id=1")
        assert r.status_code == 200
        assert r.json()["quote_required"] is True

    async def test_city_rate_wins(self, client: AsyncClient):
        tok = await _admin_token(client)
        await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "city", "city_id": 1, "amount": 2000},
        )
        r = await client.get(f"{API}/delivery/quote?city_id=1")
        body = r.json()
        assert body["scope"] == "city"
        assert body["amount"] == "2000.00"
        assert body["quote_required"] is False

    async def test_falls_back_to_region(self, client: AsyncClient):
        tok = await _admin_token(client)
        # region rate for Littoral (region 2); Kribi (city 3) has no city rate
        await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "region", "region_id": 2, "amount": 3500},
        )
        r = await client.get(f"{API}/delivery/quote?city_id=3")
        body = r.json()
        assert body["scope"] == "region"
        assert body["amount"] == "3500.00"

    async def test_missing_destination_is_422(self, client: AsyncClient):
        r = await client.get(f"{API}/delivery/quote")
        # no city_id or region_id -> service raises validation
        assert r.status_code in (400, 422)

    async def test_unknown_city_is_404(self, client: AsyncClient):
        r = await client.get(f"{API}/delivery/quote?city_id=99")
        assert r.status_code == 404


class TestRateManagement:
    async def test_creating_a_rate_supersedes_the_old(self, client: AsyncClient):
        tok = await _admin_token(client)
        await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "city", "city_id": 1, "amount": 2000},
        )
        await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "city", "city_id": 1, "amount": 2500},
        )
        # quote returns the new amount
        q = await client.get(f"{API}/delivery/quote?city_id=1")
        assert q.json()["amount"] == "2500.00"
        # only one current rate for the city
        listed = await client.get(f"{API}/admin/delivery/rates", headers=_auth(tok))
        city_rates = [r for r in listed.json() if r["city_id"] == 1]
        assert len(city_rates) == 1

    async def test_old_rate_is_kept_with_effective_to(self, client: AsyncClient):
        tok = await _admin_token(client)
        await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "city", "city_id": 1, "amount": 2000},
        )
        await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "city", "city_id": 1, "amount": 2500},
        )
        async with AsyncSessionLocal() as s:
            rows = (
                await s.execute(
                    text(
                        "SELECT amount, effective_to FROM delivery_rate "
                        "WHERE city_id=1 ORDER BY amount"
                    )
                )
            ).all()
        # two rows kept; the 2000 one is closed, the 2500 one is open
        assert len(rows) == 2
        assert rows[0].effective_to is not None   # 2000 closed
        assert rows[1].effective_to is None        # 2500 open

    async def test_city_scope_needs_city_id(self, client: AsyncClient):
        tok = await _admin_token(client)
        r = await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "city", "amount": 1000},
        )
        assert r.status_code == 422

    async def test_unknown_city_is_404(self, client: AsyncClient):
        tok = await _admin_token(client)
        r = await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "city", "city_id": 99, "amount": 1000},
        )
        assert r.status_code == 404

    async def test_update_changes_amount(self, client: AsyncClient):
        tok = await _admin_token(client)
        created = await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "city", "city_id": 1, "amount": 2000},
        )
        rate_id = created.json()["id"]
        upd = await client.patch(
            f"{API}/admin/delivery/rates/{rate_id}",
            headers=_auth(tok),
            json={"amount": 2200},
        )
        assert upd.status_code == 200
        assert upd.json()["amount"] == "2200.00"


class TestAccessControl:
    async def test_quote_is_public(self, client: AsyncClient):
        r = await client.get(f"{API}/delivery/quote?city_id=1")
        assert r.status_code == 200

    async def test_rate_write_needs_auth(self, client: AsyncClient):
        r = await client.post(
            f"{API}/admin/delivery/rates",
            json={"scope": "city", "city_id": 1, "amount": 1000},
        )
        assert r.status_code == 401

    async def test_customer_cannot_manage_rates(self, client: AsyncClient):
        tok = await _customer_token(client)
        r = await client.post(
            f"{API}/admin/delivery/rates",
            headers=_auth(tok),
            json={"scope": "city", "city_id": 1, "amount": 1000},
        )
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "permission_denied"