"""Integration tests for the catalogue module.

Covers the piece lifecycle (draft hidden -> publish -> visible), browse/search
filters, media, wishlist, publication batches, the access-control matrix, and
the reserve/release/mark_sold contract that the orders module depends on.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.main import create_app
from app.modules.catalogue.constants import PieceStatus
from app.modules.catalogue.repository import CatalogueRepository
from app.modules.catalogue.service import CatalogueService

API = "/api/v1"


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _clean() -> AsyncGenerator[None, None]:
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE piece, piece_media, house, universe, publication_batch, "
                "wishlist_item, audit_logs, refresh_tokens, device_tokens, "
                "password_reset_tokens, users RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()



class _FakeStorage:
    """In-memory storage stub for tests — no network, records puts/deletes."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, *, key: str, data: bytes, content_type: str):
        from app.core.storage.base import StoredObject

        self.objects[key] = data
        return StoredObject(key=key, url=f"http://test-storage/closet-media/{key}")

    async def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)

    def public_url(self, key: str) -> str:
        return f"http://test-storage/closet-media/{key}"


@pytest_asyncio.fixture(loop_scope="session")
async def storage() -> _FakeStorage:
    return _FakeStorage()


@pytest_asyncio.fixture(loop_scope="session")
async def client(storage: _FakeStorage) -> AsyncGenerator[AsyncClient, None]:

    app = create_app()
    app.dependency_overrides = getattr(app, "dependency_overrides", {})
    # point the catalogue service's storage at the in-memory fake

    async def _svc_with_fake_storage(db=None):
        # resolved per-request; db injected by FastAPI below
        raise RuntimeError("unused")

    # simplest override: patch get_storage to return the fake
    import app.modules.catalogue.dependencies as deps
    deps.get_storage = lambda: storage
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


async def _customer_token(client: AsyncClient, email: str = "cust@closet.cm") -> str:
    await client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Dressing2026", "full_name": "Cust"},
    )
    r = await client.post(
        f"{API}/auth/login", json={"email": email, "password": "Dressing2026"}
    )
    return r.json()["access_token"]


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


async def _make_piece(client: AsyncClient, tok: str, **over) -> dict:
    body = {"title": "Vintage Denim Jacket", "condition": "very_good", "price": 15000}
    body.update(over)
    r = await client.post(f"{API}/admin/pieces", headers=_auth(tok), json=body)
    assert r.status_code == 201, r.text
    return r.json()


class TestPieceLifecycle:
    async def test_created_piece_is_draft_and_hidden(self, client: AsyncClient):
        tok = await _admin_token(client)
        piece = await _make_piece(client, tok)
        assert piece["status"] == "draft"
        assert piece["sku"].startswith("CLO-")
        assert piece["slug"] == "vintage-denim-jacket"
        browse = await client.get(f"{API}/pieces")
        assert browse.json()["total"] == 0   # drafts don't show

    async def test_publish_makes_it_visible(self, client: AsyncClient):
        tok = await _admin_token(client)
        piece = await _make_piece(client, tok)
        pub = await client.post(
            f"{API}/admin/pieces/{piece['id']}/publish", headers=_auth(tok)
        )
        assert pub.json()["status"] == "published"
        assert pub.json()["published_at"] is not None
        browse = await client.get(f"{API}/pieces")
        assert browse.json()["total"] == 1

    async def test_cannot_publish_twice(self, client: AsyncClient):
        tok = await _admin_token(client)
        piece = await _make_piece(client, tok)
        await client.post(f"{API}/admin/pieces/{piece['id']}/publish", headers=_auth(tok))
        again = await client.post(
            f"{API}/admin/pieces/{piece['id']}/publish", headers=_auth(tok)
        )
        assert again.status_code == 409

    async def test_duplicate_sku_conflicts(self, client: AsyncClient):
        tok = await _admin_token(client)
        await _make_piece(client, tok, sku="FIXED-1")
        r = await client.post(
            f"{API}/admin/pieces",
            headers=_auth(tok),
            json={"title": "Other", "condition": "good", "price": 1, "sku": "FIXED-1"},
        )
        assert r.status_code == 409


class TestBrowseAndSearch:
    async def test_search_matches_title(self, client: AsyncClient):
        tok = await _admin_token(client)
        p = await _make_piece(client, tok, description="classic blue denim")
        await client.post(f"{API}/admin/pieces/{p['id']}/publish", headers=_auth(tok))
        hit = await client.get(f"{API}/pieces/search?q=denim")
        assert hit.json()["total"] == 1
        miss = await client.get(f"{API}/pieces/search?q=zzzznope")
        assert miss.json()["total"] == 0

    async def test_price_filter(self, client: AsyncClient):
        tok = await _admin_token(client)
        cheap = await _make_piece(client, tok, title="Cheap", price=1000)
        pricey = await _make_piece(client, tok, title="Pricey", price=90000)
        for p in (cheap, pricey):
            await client.post(f"{API}/admin/pieces/{p['id']}/publish", headers=_auth(tok))
        r = await client.get(f"{API}/pieces?max_price=5000")
        titles = [i["title"] for i in r.json()["items"]]
        assert "Cheap" in titles and "Pricey" not in titles


class TestMedia:
    async def test_upload_and_list_media(self, client: AsyncClient):
        tok = await _admin_token(client)
        p = await _make_piece(client, tok)
        files = {"file": ("photo.jpg", io.BytesIO(b"\xff\xd8\xff" + b"x" * 50), "image/jpeg")}
        add = await client.post(
            f"{API}/admin/pieces/{p['id']}/media",
            headers=_auth(tok),
            files=files,
            data={"view_label": "front"},
        )
        assert add.status_code == 201, add.text
        # url is backend-generated, not client-supplied
        assert "closet-media/pieces/" in add.json()["url"]
        detail = await client.get(f"{API}/pieces/{p['id']}")
        assert len(detail.json()["media"]) == 1

    async def test_rejects_non_image(self, client: AsyncClient):
        tok = await _admin_token(client)
        p = await _make_piece(client, tok)
        files = {"file": ("evil.txt", io.BytesIO(b"hello"), "text/plain")}
        r = await client.post(
            f"{API}/admin/pieces/{p['id']}/media", headers=_auth(tok), files=files
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "unsupported_media_type"

    async def test_delete_removes_media(self, client: AsyncClient):
        tok = await _admin_token(client)
        p = await _make_piece(client, tok)
        files = {"file": ("photo.jpg", io.BytesIO(b"\xff\xd8\xff" + b"x" * 50), "image/jpeg")}
        add = await client.post(
            f"{API}/admin/pieces/{p['id']}/media", headers=_auth(tok), files=files
        )
        mid = add.json()["id"]
        rd = await client.delete(
            f"{API}/admin/pieces/{p['id']}/media/{mid}", headers=_auth(tok)
        )
        assert rd.status_code == 204
        detail = await client.get(f"{API}/pieces/{p['id']}")
        assert len(detail.json()["media"]) == 0


class TestWishlist:
    async def test_wishlist_flow(self, client: AsyncClient):
        atok = await _admin_token(client)
        p = await _make_piece(client, atok)
        await client.post(f"{API}/admin/pieces/{p['id']}/publish", headers=_auth(atok))
        ctok = await _customer_token(client)
        add = await client.post(f"{API}/wishlist/{p['id']}", headers=_auth(ctok))
        assert add.status_code == 204
        lst = await client.get(f"{API}/wishlist", headers=_auth(ctok))
        assert len(lst.json()) == 1
        detail = await client.get(f"{API}/pieces/{p['id']}", headers=_auth(ctok))
        assert detail.json()["in_wishlist"] is True
        rm = await client.delete(f"{API}/wishlist/{p['id']}", headers=_auth(ctok))
        assert rm.status_code == 204

    async def test_detail_without_auth_has_no_wishlist_flag(self, client: AsyncClient):
        tok = await _admin_token(client)
        p = await _make_piece(client, tok)
        await client.post(f"{API}/admin/pieces/{p['id']}/publish", headers=_auth(tok))
        detail = await client.get(f"{API}/pieces/{p['id']}")
        assert detail.json()["in_wishlist"] is False


class TestPublicationBatch:
    async def test_batch_publishes_all(self, client: AsyncClient):
        tok = await _admin_token(client)
        p1 = await _make_piece(client, tok, title="A")
        p2 = await _make_piece(client, tok, title="B")
        r = await client.post(
            f"{API}/admin/publication-batches",
            headers=_auth(tok),
            json={"label": "Drop", "piece_ids": [p1["id"], p2["id"]]},
        )
        assert r.status_code == 201
        assert (await client.get(f"{API}/pieces")).json()["total"] == 2


class TestAccessControl:
    async def test_browse_is_public(self, client: AsyncClient):
        assert (await client.get(f"{API}/pieces")).status_code == 200

    async def test_customer_cannot_create(self, client: AsyncClient):
        tok = await _customer_token(client)
        r = await client.post(
            f"{API}/admin/pieces",
            headers=_auth(tok),
            json={"title": "x", "condition": "good", "price": 100},
        )
        assert r.status_code == 403

    async def test_write_needs_auth(self, client: AsyncClient):
        r = await client.post(
            f"{API}/admin/pieces",
            json={"title": "x", "condition": "good", "price": 100},
        )
        assert r.status_code == 401


class TestReservationContract:
    """The reserve/release/mark_sold methods orders will call."""

    async def test_reserve_release_sold_cycle(self, client: AsyncClient):
        tok = await _admin_token(client)
        p = await _make_piece(client, tok)
        await client.post(f"{API}/admin/pieces/{p['id']}/publish", headers=_auth(tok))
        pid = uuid.UUID(p["id"])
        order_id = uuid.uuid4()

        async def status_of() -> str:
            async with AsyncSessionLocal() as db:
                piece = await CatalogueRepository(db).get_piece(pid)
                return piece.status.value

        # reserve
        async with AsyncSessionLocal() as db:
            ok = await CatalogueService(CatalogueRepository(db)).reserve(
                pid, order_id=order_id
            )
            await db.commit()
        assert ok is True
        assert await status_of() == PieceStatus.RESERVED.value

        # double reserve is refused
        async with AsyncSessionLocal() as db:
            ok2 = await CatalogueService(CatalogueRepository(db)).reserve(
                pid, order_id=uuid.uuid4()
            )
        assert ok2 is False

        # release returns to published
        async with AsyncSessionLocal() as db:
            await CatalogueService(CatalogueRepository(db)).release(pid)
            await db.commit()
        assert await status_of() == PieceStatus.PUBLISHED.value

        # reserve then mark sold
        async with AsyncSessionLocal() as db:
            svc = CatalogueService(CatalogueRepository(db))
            await svc.reserve(pid, order_id=order_id)
            await db.commit()
        async with AsyncSessionLocal() as db:
            await CatalogueService(CatalogueRepository(db)).mark_sold(pid)
            await db.commit()
        assert await status_of() == PieceStatus.SOLD.value

        # a sold piece cannot be reserved
        async with AsyncSessionLocal() as db:
            ok3 = await CatalogueService(CatalogueRepository(db)).reserve(
                pid, order_id=uuid.uuid4()
            )
        assert ok3 is False
