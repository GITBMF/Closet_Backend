from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.modules.showcasing.models import Sponsor, FeaturedSlot


class ShowcasingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Public Read Methods ---
    async def get_active_sponsors(self) -> List[Sponsor]:
        now = datetime.now(timezone.utc)
        query = select(Sponsor).where(
            Sponsor.is_active == True,
            (Sponsor.starts_at == None) | (Sponsor.starts_at <= now),
            (Sponsor.ends_at == None) | (Sponsor.ends_at >= now)
        )
        result = await self.db.scalars(query)
        return list(result.all())

    async def get_active_featured_slots(self, slot_type: Optional[str] = None) -> List[FeaturedSlot]:
        now = datetime.now(timezone.utc)
        query = select(FeaturedSlot).options(selectinload(FeaturedSlot.piece)).where(
            (FeaturedSlot.starts_at == None) | (FeaturedSlot.starts_at <= now),
            (FeaturedSlot.ends_at == None) | (FeaturedSlot.ends_at >= now)
        )
        if slot_type:
            query = query.where(FeaturedSlot.slot_type == slot_type)
            
        result = await self.db.scalars(query.order_by(FeaturedSlot.position))
        return list(result.all())

    # --- Admin Sponsor CRUD ---
    async def get_all_sponsors(self) -> List[Sponsor]:
        result = await self.db.scalars(select(Sponsor))
        return list(result.all())

    async def get_sponsor_by_id(self, sponsor_id: UUID) -> Optional[Sponsor]:
        return await self.db.get(Sponsor, sponsor_id)

    async def create_sponsor(self, sponsor_data: dict) -> Sponsor:
        sponsor = Sponsor(**sponsor_data)
        self.db.add(sponsor)
        await self.db.commit()
        await self.db.refresh(sponsor)
        return sponsor

    async def update_sponsor(self, sponsor: Sponsor, update_data: dict) -> Sponsor:
        for field, value in update_data.items():
            if value is not None:
                setattr(sponsor, field, value)
        await self.db.commit()
        await self.db.refresh(sponsor)
        return sponsor

    async def delete_sponsor(self, sponsor: Sponsor) -> bool:
        await self.db.delete(sponsor)
        await self.db.commit()
        return True

    # --- Admin Featured Slot CRUD ---
    async def get_all_featured_slots(self) -> List[FeaturedSlot]:
        query = select(FeaturedSlot).options(selectinload(FeaturedSlot.piece))
        result = await self.db.scalars(query)
        return list(result.all())

    async def get_featured_slot_by_id(self, slot_id: int) -> Optional[FeaturedSlot]:
        query = select(FeaturedSlot).options(selectinload(FeaturedSlot.piece)).where(FeaturedSlot.id == slot_id)
        return await self.db.scalar(query)

    async def create_featured_slot(self, slot_data: dict, user_id: Optional[UUID] = None) -> FeaturedSlot:
        slot = FeaturedSlot(**slot_data, created_by=user_id)
        self.db.add(slot)
        await self.db.commit()
        await self.db.refresh(slot)
        return slot

    async def update_featured_slot(self, slot: FeaturedSlot, update_data: dict) -> FeaturedSlot:
        for field, value in update_data.items():
            if value is not None:
                setattr(slot, field, value)
        await self.db.commit()
        await self.db.refresh(slot)
        return slot

    async def delete_featured_slot(self, slot: FeaturedSlot) -> bool:
        await self.db.delete(slot)
        await self.db.commit()
        return True