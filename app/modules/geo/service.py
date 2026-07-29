"""Geo service — reference reads and delivery-zone management.

Geo is mostly read-only reference data. The write paths (adding a fixed-rate
city or a neighbourhood) exist so the administrator can open a new delivery
zone without a deploy. Each write validates its parent exists and guards the
uniqueness the DB also enforces, so the caller gets a clean 409 instead of a
raw integrity error.
"""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.modules.geo.models import FixedRateCity, Neighbourhood
from app.modules.geo.repository import GeoRepository
from app.modules.geo.schemas import (
    CityCreate,
    CityUpdate,
    NeighbourhoodCreate,
    NeighbourhoodUpdate,
)


class GeoService:
    def __init__(self, repo: GeoRepository) -> None:
        self.repo = repo

    # ----------------------------------------------------------- reads
    async def list_regions(self):
        return await self.repo.list_regions()

    async def list_divisions(self, region_id: int):
        if await self.repo.get_region(region_id) is None:
            raise NotFoundError("Région introuvable.", code="region_not_found")
        return await self.repo.list_divisions(region_id)

    async def list_subdivisions(self, division_id: int):
        return await self.repo.list_subdivisions(division_id)

    async def list_cities(self, *, active_only: bool = True):
        return await self.repo.list_cities(active_only=active_only)

    async def list_neighbourhoods(self, city_id: int, *, active_only: bool = True):
        if await self.repo.get_city(city_id) is None:
            raise NotFoundError("Ville introuvable.", code="city_not_found")
        return await self.repo.list_neighbourhoods(city_id, active_only=active_only)

    # ---------------------------------------------------------- writes
    async def create_city(self, payload: CityCreate) -> FixedRateCity:
        if await self.repo.get_region(payload.region_id) is None:
            raise NotFoundError("Région introuvable.", code="region_not_found")
        city = FixedRateCity(
            name=payload.name.strip(),
            region_id=payload.region_id,
            is_active=payload.is_active,
        )
        city = await self.repo.add_city(city)
        await self.repo.db.commit()
        await self.repo.db.refresh(city)
        return city

    async def update_city(self, city_id: int, payload: CityUpdate) -> FixedRateCity:
        city = await self.repo.get_city(city_id)
        if city is None:
            raise NotFoundError("Ville introuvable.", code="city_not_found")
        if payload.region_id is not None:
            if await self.repo.get_region(payload.region_id) is None:
                raise NotFoundError("Région introuvable.", code="region_not_found")
            city.region_id = payload.region_id
        if payload.name is not None:
            city.name = payload.name.strip()
        if payload.is_active is not None:
            city.is_active = payload.is_active
        await self.repo.db.commit()
        await self.repo.db.refresh(city)
        return city

    async def create_neighbourhood(self, payload: NeighbourhoodCreate) -> Neighbourhood:
        if await self.repo.get_city(payload.city_id) is None:
            raise NotFoundError("Ville introuvable.", code="city_not_found")
        n = Neighbourhood(
            city_id=payload.city_id,
            name=payload.name.strip(),
            is_active=payload.is_active,
        )
        n = await self.repo.add_neighbourhood(n)
        await self.repo.db.commit()
        await self.repo.db.refresh(n)
        return n

    async def update_neighbourhood(
        self, neighbourhood_id: int, payload: NeighbourhoodUpdate
    ) -> Neighbourhood:
        n = await self.repo.get_neighbourhood(neighbourhood_id)
        if n is None:
            raise NotFoundError("Quartier introuvable.", code="neighbourhood_not_found")
        if payload.name is not None:
            n.name = payload.name.strip()
        if payload.is_active is not None:
            n.is_active = payload.is_active
        await self.repo.db.commit()
        await self.repo.db.refresh(n)
        return n