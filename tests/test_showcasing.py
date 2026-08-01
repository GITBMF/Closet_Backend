"""Integration tests for the showcasing module.

Covers sponsors and featured slots against real tables: creation, the public
home endpoint resolving pieces THROUGH the catalogue service, the published-only
rule (a slot pointing at a non-published piece is hidden from the public but
visible to admins), time-window filtering, and validation (missing piece,
inverted date window).

Cross-module reads go through CatalogueService, matching the module under test.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.catalogue.repository import CatalogueRepository
from app.modules.catalogue.service import CatalogueService
from app.modules.showcasing.constants import FeaturedSlotType
from app.modules.showcasing.repository import ShowcasingRepository
from app.modules.showcasing.schemas import (
    FeaturedSlotCreate,
    SponsorCreate,
    SponsorUpdate,
)
from app.modules.showcasing.service import ShowcasingService


def _svc(db) -> ShowcasingService:
    cat = CatalogueService(CatalogueRepository(db), storage=None)
    return ShowcasingService(ShowcasingRepository(db), cat)


async def _seed_piece(status: str = "published") -> uuid.UUID:
    pid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO piece (id,title,slug,price,status,sku,condition,currency) "
                "VALUES (:id,'Vintage Coat',:slug,50000,:st,:sku,'good','XAF')"
            ),
            {
                "id": pid,
                "slug": f"coat-{uuid.uuid4().hex[:6]}",
                "st": status,
                "sku": f"CLO-{uuid.uuid4().hex[:6]}",
            },
        )
        await s.commit()
    return pid


async def _seed_admin() -> uuid.UUID:
    aid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_active) "
                "VALUES (:i,:e,'Admin','admin',true)"
            ),
            {"i": aid, "e": f"admin-{aid.hex[:6]}@c.cm"},
        )
        await s.commit()
    return aid


@pytest_asyncio.fixture(autouse=True)
async def _clean() -> AsyncGenerator[None, None]:
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE featured_slot, sponsor, piece, users RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()


class TestSponsors:
    async def test_create_and_list(self):
        async with AsyncSessionLocal() as db:
            sp = await _svc(db).create_sponsor(
                SponsorCreate(name="Douala Fashion Week", logo_url="https://x/l.png", position=1)
            )
        assert sp.name == "Douala Fashion Week"
        assert sp.position == 1
        assert sp.is_active is True

    async def test_expired_sponsor_hidden_from_public_shown_to_admin(self):
        async with AsyncSessionLocal() as db:
            await _svc(db).create_sponsor(
                SponsorCreate(name="Live", logo_url="x")
            )
            await _svc(db).create_sponsor(
                SponsorCreate(
                    name="Expired", logo_url="x",
                    starts_at=datetime.now(UTC) - timedelta(days=10),
                    ends_at=datetime.now(UTC) - timedelta(days=1),
                )
            )
        async with AsyncSessionLocal() as db:
            public = await _svc(db).active_sponsors()
        async with AsyncSessionLocal() as db:
            all_ = await _svc(db).list_sponsors()
        assert len(public) == 1        # only the live one
        assert len(all_) == 2          # admin sees both

    async def test_inverted_window_rejected(self):
        with pytest.raises(ValidationError):
            async with AsyncSessionLocal() as db:
                await _svc(db).create_sponsor(
                    SponsorCreate(
                        name="Bad", logo_url="x",
                        starts_at=datetime.now(UTC),
                        ends_at=datetime.now(UTC) - timedelta(days=1),
                    )
                )

    async def test_update_and_delete(self):
        async with AsyncSessionLocal() as db:
            sp = await _svc(db).create_sponsor(SponsorCreate(name="X", logo_url="x"))
            sid = sp.id
        async with AsyncSessionLocal() as db:
            await _svc(db).update_sponsor(sid, SponsorUpdate(name="DFW 2026", position=5))
        async with AsyncSessionLocal() as db:
            got = await _svc(db).repo.get_sponsor(sid)
        assert got.name == "DFW 2026"
        assert got.position == 5
        async with AsyncSessionLocal() as db:
            await _svc(db).delete_sponsor(sid)
        async with AsyncSessionLocal() as db:
            assert await _svc(db).repo.get_sponsor(sid) is None

    async def test_delete_unknown_sponsor_raises(self):
        with pytest.raises(NotFoundError):
            async with AsyncSessionLocal() as db:
                await _svc(db).delete_sponsor(uuid.uuid4())


class TestFeaturedSlots:
    async def test_create_on_published_piece(self):
        pid = await _seed_piece("published")
        admin = await _seed_admin()
        async with AsyncSessionLocal() as db:
            slot = await _svc(db).create_featured(
                FeaturedSlotCreate(slot=FeaturedSlotType.HERO, piece_id=pid),
                created_by=admin,
            )
        assert slot.slot is FeaturedSlotType.HERO
        assert slot.piece_id == pid
        assert slot.created_by == admin

    async def test_create_on_missing_piece_raises(self):
        admin = await _seed_admin()
        with pytest.raises(NotFoundError):
            async with AsyncSessionLocal() as db:
                await _svc(db).create_featured(
                    FeaturedSlotCreate(slot=FeaturedSlotType.HERO, piece_id=uuid.uuid4()),
                    created_by=admin,
                )

    async def test_public_home_resolves_pieces_via_catalogue(self):
        pid = await _seed_piece("published")
        admin = await _seed_admin()
        async with AsyncSessionLocal() as db:
            await _svc(db).create_sponsor(SponsorCreate(name="S", logo_url="x"))
            await _svc(db).create_featured(
                FeaturedSlotCreate(slot=FeaturedSlotType.HERO, piece_id=pid),
                created_by=admin,
            )
        async with AsyncSessionLocal() as db:
            sponsors, featured = await _svc(db).home()
        assert len(sponsors) == 1
        assert len(featured) == 1
        slot, piece = featured[0]
        assert slot.slot is FeaturedSlotType.HERO
        assert piece is not None
        assert piece.title == "Vintage Coat"

    async def test_draft_piece_slot_hidden_from_public_but_visible_to_admin(self):
        published = await _seed_piece("published")
        draft = await _seed_piece("draft")
        admin = await _seed_admin()
        async with AsyncSessionLocal() as db:
            await _svc(db).create_featured(
                FeaturedSlotCreate(slot=FeaturedSlotType.HERO, piece_id=published),
                created_by=admin,
            )
            await _svc(db).create_featured(
                FeaturedSlotCreate(slot=FeaturedSlotType.FAVOURITE, piece_id=draft),
                created_by=admin,
            )
        async with AsyncSessionLocal() as db:
            public = await _svc(db).active_featured()
        async with AsyncSessionLocal() as db:
            admin_all = await _svc(db).list_featured()
        assert len(public) == 1        # draft one filtered out of public
        assert len(admin_all) == 2     # admin sees both

    async def test_filter_by_slot_type(self):
        p1 = await _seed_piece("published")
        p2 = await _seed_piece("published")
        admin = await _seed_admin()
        async with AsyncSessionLocal() as db:
            await _svc(db).create_featured(
                FeaturedSlotCreate(slot=FeaturedSlotType.HERO, piece_id=p1), created_by=admin
            )
            await _svc(db).create_featured(
                FeaturedSlotCreate(slot=FeaturedSlotType.FAVOURITE, piece_id=p2), created_by=admin
            )
        async with AsyncSessionLocal() as db:
            heroes = await _svc(db).active_featured(FeaturedSlotType.HERO)
        assert len(heroes) == 1
        assert heroes[0][0].slot is FeaturedSlotType.HERO

    async def test_delete_unknown_slot_raises(self):
        with pytest.raises(NotFoundError):
            async with AsyncSessionLocal() as db:
                await _svc(db).delete_featured(999999)
