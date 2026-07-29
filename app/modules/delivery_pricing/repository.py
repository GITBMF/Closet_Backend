"""Delivery-pricing repository — the only place rate SQL lives.

"Current" means: effective_from <= now AND (effective_to IS NULL OR
effective_to > now). Superseding a rate is done by stamping the old row's
effective_to, never by editing its amount — so history is preserved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.delivery_pricing.constants import DeliveryScope
from app.modules.delivery_pricing.models import DeliveryRate


def _is_current(now: datetime):
    return and_(
        DeliveryRate.effective_from <= now,
        or_(DeliveryRate.effective_to.is_(None), DeliveryRate.effective_to > now),
    )


class DeliveryPricingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def current_city_rate(self, city_id: int) -> DeliveryRate | None:
        now = datetime.now(UTC)
        stmt = (
            select(DeliveryRate)
            .where(
                DeliveryRate.scope == DeliveryScope.CITY,
                DeliveryRate.city_id == city_id,
                _is_current(now),
            )
            .order_by(DeliveryRate.effective_from.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def current_region_rate(self, region_id: int) -> DeliveryRate | None:
        now = datetime.now(UTC)
        stmt = (
            select(DeliveryRate)
            .where(
                DeliveryRate.scope == DeliveryScope.REGION,
                DeliveryRate.region_id == region_id,
                _is_current(now),
            )
            .order_by(DeliveryRate.effective_from.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get(self, rate_id: int) -> DeliveryRate | None:
        return await self.db.get(DeliveryRate, rate_id)

    async def list_current(self) -> list[DeliveryRate]:
        now = datetime.now(UTC)
        stmt = (
            select(DeliveryRate)
            .where(_is_current(now))
            .order_by(DeliveryRate.scope, DeliveryRate.effective_from.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def find_current_for_target(
        self, scope: DeliveryScope, *, city_id: int | None, region_id: int | None
    ) -> DeliveryRate | None:
        if scope is DeliveryScope.CITY and city_id is not None:
            return await self.current_city_rate(city_id)
        if scope is DeliveryScope.REGION and region_id is not None:
            return await self.current_region_rate(region_id)
        return None

    async def supersede(
        self, old: DeliveryRate, *, at: datetime
    ) -> None:
        """Close a rate's validity window (used when a new one replaces it)."""
        old.effective_to = at
        await self.db.flush()

    async def add(self, rate: DeliveryRate) -> DeliveryRate:
        self.db.add(rate)
        await self.db.flush()
        return rate

    async def create_rate(
        self,
        *,
        scope: DeliveryScope,
        city_id: int | None,
        region_id: int | None,
        amount: Decimal,
        currency: str,
        created_by: uuid.UUID | None,
    ) -> DeliveryRate:
        rate = DeliveryRate(
            scope=scope,
            city_id=city_id,
            region_id=region_id,
            amount=amount,
            currency=currency,
            created_by=created_by,
        )
        return await self.add(rate)