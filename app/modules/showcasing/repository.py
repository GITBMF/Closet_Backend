"""Showcasing repository — sponsor + featured-slot SQL.

Writes flush but do NOT commit; the service owns the transaction boundary,
matching every other module. Reads that need the piece resolve it through the
catalogue SERVICE (in the service layer), not by joining catalogue tables here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.showcasing.constants import FeaturedSlotType
from app.modules.showcasing.models import FeaturedSlot, Sponsor


def _active_window(column_start, column_end, now):
    return (
        ((column_start.is_(None)) | (column_start <= now))
        & ((column_end.is_(None)) | (column_end >= now))
    )


class ShowcasingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------- sponsors (read)
    async def active_sponsors(self) -> list[Sponsor]:
        now = datetime.now(UTC)
        stmt = (
            select(Sponsor)
            .where(Sponsor.is_active.is_(True))
            .where(_active_window(Sponsor.starts_at, Sponsor.ends_at, now))
            .order_by(Sponsor.position, Sponsor.created_at)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def all_sponsors(self) -> list[Sponsor]:
        stmt = select(Sponsor).order_by(Sponsor.position, Sponsor.created_at)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_sponsor(self, sponsor_id: uuid.UUID) -> Sponsor | None:
        return await self.db.get(Sponsor, sponsor_id)

    # --------------------------------------------------- sponsors (write)
    async def add_sponsor(self, sponsor: Sponsor) -> Sponsor:
        self.db.add(sponsor)
        await self.db.flush()
        return sponsor

    async def delete_sponsor(self, sponsor: Sponsor) -> None:
        await self.db.delete(sponsor)
        await self.db.flush()

    # ---------------------------------------------- featured slots (read)
    async def active_featured(
        self, slot: FeaturedSlotType | None = None
    ) -> list[FeaturedSlot]:
        now = datetime.now(UTC)
        stmt = (
            select(FeaturedSlot)
            .where(_active_window(FeaturedSlot.starts_at, FeaturedSlot.ends_at, now))
            .order_by(FeaturedSlot.created_at)
        )
        if slot is not None:
            stmt = stmt.where(FeaturedSlot.slot == slot)
        return list((await self.db.execute(stmt)).scalars().all())

    async def all_featured(self) -> list[FeaturedSlot]:
        stmt = select(FeaturedSlot).order_by(FeaturedSlot.created_at)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_featured(self, slot_id: int) -> FeaturedSlot | None:
        return await self.db.get(FeaturedSlot, slot_id)

    # --------------------------------------------- featured slots (write)
    async def add_featured(self, slot: FeaturedSlot) -> FeaturedSlot:
        self.db.add(slot)
        await self.db.flush()
        return slot

    async def delete_featured(self, slot: FeaturedSlot) -> None:
        await self.db.delete(slot)
        await self.db.flush()