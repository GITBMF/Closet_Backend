"""Geo HTTP layer.

Two routers:
  * `router`       -> /geo/*        public reference reads (no auth)
  * `admin_router` -> /admin/geo/*  delivery-zone management (GEO_MANAGE)

The read endpoints are public because the customer app needs the region /
city / neighbourhood lists to build address forms and delivery quotes before
the user has logged in.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.modules.geo.dependencies import Service
from app.modules.geo.schemas import (
    CityCreate,
    CityOut,
    CityUpdate,
    DivisionOut,
    NeighbourhoodCreate,
    NeighbourhoodOut,
    NeighbourhoodUpdate,
    RegionOut,
    SubdivisionOut,
)
from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import require_permission

router = APIRouter(prefix="/geo", tags=["geo"])
admin_router = APIRouter(
    prefix="/admin/geo",
    tags=["admin: geo"],
    dependencies=[Depends(require_permission(Permission.GEO_MANAGE))],
)


# ----------------------------------------------------------- public reads
@router.get("/regions", response_model=list[RegionOut])
async def list_regions(service: Service) -> list[RegionOut]:
    return [RegionOut.model_validate(r) for r in await service.list_regions()]


@router.get("/regions/{region_id}/divisions", response_model=list[DivisionOut])
async def list_divisions(region_id: int, service: Service) -> list[DivisionOut]:
    rows = await service.list_divisions(region_id)
    return [DivisionOut.model_validate(d) for d in rows]


@router.get("/divisions/{division_id}/subdivisions", response_model=list[SubdivisionOut])
async def list_subdivisions(division_id: int, service: Service) -> list[SubdivisionOut]:
    rows = await service.list_subdivisions(division_id)
    return [SubdivisionOut.model_validate(s) for s in rows]


@router.get("/cities", response_model=list[CityOut])
async def list_cities(
    service: Service,
    active_only: Annotated[bool, Query()] = True,
) -> list[CityOut]:
    rows = await service.list_cities(active_only=active_only)
    return [CityOut.model_validate(c) for c in rows]


@router.get("/cities/{city_id}/neighbourhoods", response_model=list[NeighbourhoodOut])
async def list_neighbourhoods(
    city_id: int,
    service: Service,
    active_only: Annotated[bool, Query()] = True,
) -> list[NeighbourhoodOut]:
    rows = await service.list_neighbourhoods(city_id, active_only=active_only)
    return [NeighbourhoodOut.model_validate(n) for n in rows]


# ------------------------------------------------------ admin: zone management
@admin_router.post(
    "/cities", response_model=CityOut, status_code=status.HTTP_201_CREATED
)
async def create_city(
    payload: CityCreate, service: Service
) -> CityOut:
    return CityOut.model_validate(await service.create_city(payload))


@admin_router.patch("/cities/{city_id}", response_model=CityOut)
async def update_city(
    city_id: int,
    payload: CityUpdate,
    service: Service,
) -> CityOut:
    return CityOut.model_validate(await service.update_city(city_id, payload))


@admin_router.post(
    "/neighbourhoods",
    response_model=NeighbourhoodOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_neighbourhood(
    payload: NeighbourhoodCreate,
    service: Service,
) -> NeighbourhoodOut:
    return NeighbourhoodOut.model_validate(await service.create_neighbourhood(payload))


@admin_router.patch("/neighbourhoods/{neighbourhood_id}", response_model=NeighbourhoodOut)
async def update_neighbourhood(
    neighbourhood_id: int,
    payload: NeighbourhoodUpdate,
    service: Service,
) -> NeighbourhoodOut:
    return NeighbourhoodOut.model_validate(
        await service.update_neighbourhood(neighbourhood_id, payload)
    )