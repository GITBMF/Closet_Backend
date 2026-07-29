"""Integration tests for the geo module.

Runs against a real PostgreSQL (the schema fixture in conftest builds it).
Covers the public reference reads, the admin zone-management writes, and the
access-control matrix: reads are open, writes need the GEO_MANAGE permission.
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
    """Seed a small geo tree before each test; clean everything after."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO region (name, code) VALUES "
                "('Centre','CE'), ('Littoral','LT')"
            )
        )
        await s.execute(
            text(
                "INSERT INTO division (region_id, name) VALUES "
                "(1,'Mfoundi'), (2,'Wouri')"
            )
        )
        await s.execute(
            text(
                "INSERT INTO subdivision (division_id, name) VALUES "
                "(1,'Yaoundé I'), (1,'Yaoundé II')"
            )
        )
        await s.execute(
            text(
                "INSERT INTO fixed_rate_city (name, region_id, is_active) VALUES "
                "('Yaoundé',1,true), ('Douala',2,true)"
            )
        )
        await s.execute(
            text(
                "INSERT INTO neighbourhood (city_id, name, is_active) VALUES "
                "(1,'Bastos',true), (1,'Mvog-Mbi',true)"
            )
        )
        await s.commit()
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE region, division, subdivision, fixed_rate_city, "
                "neighbourhood, audit_logs, refresh_tokens, device_tokens, "
                "password_reset_tokens, users RESTART IDENTITY CASCADE"
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


class TestPublicReads:
    async def test_list_regions(self, client: AsyncClient):
        r = await client.get(f"{API}/geo/regions")
        assert r.status_code == 200
        names = [x["name"] for x in r.json()]
        assert names == ["Centre", "Littoral"]   # alphabetical

    async def test_divisions_of_region(self, client: AsyncClient):
        r = await client.get(f"{API}/geo/regions/1/divisions")
        assert r.status_code == 200
        assert r.json()[0]["name"] == "Mfoundi"

    async def test_divisions_of_missing_region_is_404(self, client: AsyncClient):
        r = await client.get(f"{API}/geo/regions/99/divisions")
        assert r.status_code == 404

    async def test_subdivisions(self, client: AsyncClient):
        r = await client.get(f"{API}/geo/divisions/1/subdivisions")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_list_cities(self, client: AsyncClient):
        r = await client.get(f"{API}/geo/cities")
        assert r.status_code == 200
        assert {c["name"] for c in r.json()} == {"Yaoundé", "Douala"}

    async def test_neighbourhoods(self, client: AsyncClient):
        r = await client.get(f"{API}/geo/cities/1/neighbourhoods")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_neighbourhoods_of_missing_city_is_404(self, client: AsyncClient):
        r = await client.get(f"{API}/geo/cities/99/neighbourhoods")
        assert r.status_code == 404


class TestAdminWrites:
    async def test_create_city(self, client: AsyncClient):
        tok = await _admin_token(client)
        r = await client.post(
            f"{API}/admin/geo/cities",
            headers={"Authorization": f"Bearer {tok}"},
            json={"name": "Bafoussam", "region_id": 1},
        )
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "Bafoussam"

    async def test_create_city_bad_region_is_404(self, client: AsyncClient):
        tok = await _admin_token(client)
        r = await client.post(
            f"{API}/admin/geo/cities",
            headers={"Authorization": f"Bearer {tok}"},
            json={"name": "Nowhere", "region_id": 99},
        )
        assert r.status_code == 404

    async def test_deactivating_a_city_hides_it(self, client: AsyncClient):
        tok = await _admin_token(client)
        patch = await client.patch(
            f"{API}/admin/geo/cities/1",
            headers={"Authorization": f"Bearer {tok}"},
            json={"is_active": False},
        )
        assert patch.status_code == 200
        listed = await client.get(f"{API}/geo/cities?active_only=true")
        assert "Yaoundé" not in {c["name"] for c in listed.json()}
        # but visible when active_only=false
        all_ = await client.get(f"{API}/geo/cities?active_only=false")
        assert "Yaoundé" in {c["name"] for c in all_.json()}

    async def test_create_neighbourhood(self, client: AsyncClient):
        tok = await _admin_token(client)
        r = await client.post(
            f"{API}/admin/geo/neighbourhoods",
            headers={"Authorization": f"Bearer {tok}"},
            json={"city_id": 1, "name": "Nlongkak"},
        )
        assert r.status_code == 201


class TestAccessControl:
    async def test_write_requires_auth(self, client: AsyncClient):
        r = await client.post(
            f"{API}/admin/geo/cities", json={"name": "X", "region_id": 1}
        )
        assert r.status_code == 401

    async def test_customer_cannot_write(self, client: AsyncClient):
        tok = await _customer_token(client)
        r = await client.post(
            f"{API}/admin/geo/cities",
            headers={"Authorization": f"Bearer {tok}"},
            json={"name": "X", "region_id": 1},
        )
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "permission_denied"

    async def test_reads_need_no_auth(self, client: AsyncClient):
        r = await client.get(f"{API}/geo/regions")
        assert r.status_code == 200