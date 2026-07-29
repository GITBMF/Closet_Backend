"""Geo repository — the only place geo SQL lives.

Reference reads and the small set of admin writes for delivery zones.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.geo.models import (
    Division,
    FixedRateCity,
    Neighbourhood,
    Region,
    Subdivision,
)


class GeoRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----------------------------------------------------------- reads
    async def list_regions(self) -> list[Region]:
        stmt = select(Region).order_by(Region.name)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_region(self, region_id: int) -> Region | None:
        return await self.db.get(Region, region_id)

    async def list_divisions(self, region_id: int) -> list[Division]:
        stmt = (
            select(Division)
            .where(Division.region_id == region_id)
            .order_by(Division.name)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_subdivisions(self, division_id: int) -> list[Subdivision]:
        stmt = (
            select(Subdivision)
            .where(Subdivision.division_id == division_id)
            .order_by(Subdivision.name)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_cities(self, *, active_only: bool = True) -> list[FixedRateCity]:
        stmt = select(FixedRateCity).order_by(FixedRateCity.name)
        if active_only:
            stmt = stmt.where(FixedRateCity.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_city(self, city_id: int) -> FixedRateCity | None:
        return await self.db.get(FixedRateCity, city_id)

    async def list_neighbourhoods(
        self, city_id: int, *, active_only: bool = True
    ) -> list[Neighbourhood]:
        stmt = (
            select(Neighbourhood)
            .where(Neighbourhood.city_id == city_id)
            .order_by(Neighbourhood.name)
        )
        if active_only:
            stmt = stmt.where(Neighbourhood.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_neighbourhood(self, neighbourhood_id: int) -> Neighbourhood | None:
        return await self.db.get(Neighbourhood, neighbourhood_id)

    # ---------------------------------------------------------- writes
    async def add_city(self, city: FixedRateCity) -> FixedRateCity:
        self.db.add(city)
        await self.db.flush()
        return city

    async def add_neighbourhood(self, n: Neighbourhood) -> Neighbourhood:
        self.db.add(n)
        await self.db.flush()
        return n