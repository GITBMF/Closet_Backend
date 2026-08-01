"""Showcasing HTTP layer.

  * router       -> /showcasing/*         public storefront (home, sponsors, featured)
  * admin_router -> /admin/showcasing/*   sponsor + featured-slot management

Admin writes are guarded by the real permissions (sponsor:manage /
showcase:manage) — not merely "any logged-in user". Public reads only ever
surface published pieces (enforced in the service).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import CurrentUser, require_permission
from app.modules.showcasing.constants import FeaturedSlotType
from app.modules.showcasing.dependencies import Service
from app.modules.showcasing.schemas import (
    FeaturedSlotCreate,
    FeaturedSlotOut,
    FeaturedSlotUpdate,
    FeaturedSlotWithPiece,
    HomeShowcase,
    SponsorCreate,
    SponsorOut,
    SponsorUpdate,
)

router = APIRouter(prefix="/showcasing", tags=["showcasing"])
admin_router = APIRouter(prefix="/admin/showcasing", tags=["admin: showcasing"])

_SPONSOR = Depends(require_permission(Permission.SPONSOR_MANAGE))
_SHOWCASE = Depends(require_permission(Permission.SHOWCASE_MANAGE))


def _with_piece(slot, piece) -> FeaturedSlotWithPiece:
    out = FeaturedSlotWithPiece.model_validate(slot)
    out.piece = piece  # PieceSummary validated from the ORM piece
    return out


# ================================================================= public
@router.get("/home", response_model=HomeShowcase)
async def home(service: Service) -> HomeShowcase:
    sponsors, featured = await service.home()
    return HomeShowcase(
        sponsors=[SponsorOut.model_validate(s) for s in sponsors],
        featured=[_with_piece(slot, piece) for slot, piece in featured],
    )


@router.get("/sponsors", response_model=list[SponsorOut])
async def public_sponsors(service: Service) -> list[SponsorOut]:
    return [SponsorOut.model_validate(s) for s in await service.active_sponsors()]


@router.get("/featured", response_model=list[FeaturedSlotWithPiece])
async def public_featured(
    service: Service,
    slot: Annotated[FeaturedSlotType | None, Query()] = None,
) -> list[FeaturedSlotWithPiece]:
    return [_with_piece(s, p) for s, p in await service.active_featured(slot)]


# ============================================= admin: sponsors (sponsor:manage)
@admin_router.get("/sponsors", response_model=list[SponsorOut], dependencies=[_SPONSOR])
async def list_sponsors(service: Service) -> list[SponsorOut]:
    return [SponsorOut.model_validate(s) for s in await service.list_sponsors()]


@admin_router.post("/sponsors", response_model=SponsorOut,
                   status_code=status.HTTP_201_CREATED, dependencies=[_SPONSOR])
async def create_sponsor(payload: SponsorCreate, service: Service) -> SponsorOut:
    return SponsorOut.model_validate(await service.create_sponsor(payload))


@admin_router.patch("/sponsors/{sponsor_id}", response_model=SponsorOut,
                    dependencies=[_SPONSOR])
async def update_sponsor(
    sponsor_id: uuid.UUID, payload: SponsorUpdate, service: Service
) -> SponsorOut:
    return SponsorOut.model_validate(await service.update_sponsor(sponsor_id, payload))


@admin_router.delete("/sponsors/{sponsor_id}",
                     status_code=status.HTTP_204_NO_CONTENT,
                     response_class=Response, dependencies=[_SPONSOR])
async def delete_sponsor(sponsor_id: uuid.UUID, service: Service) -> Response:
    await service.delete_sponsor(sponsor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ====================================== admin: featured slots (showcase:manage)
@admin_router.get("/featured", response_model=list[FeaturedSlotWithPiece],
                  dependencies=[_SHOWCASE])
async def list_featured(service: Service) -> list[FeaturedSlotWithPiece]:
    return [_with_piece(s, p) for s, p in await service.list_featured()]


@admin_router.post("/featured", response_model=FeaturedSlotOut,
                   status_code=status.HTTP_201_CREATED, dependencies=[_SHOWCASE])
async def create_featured(
    payload: FeaturedSlotCreate, service: Service, user: CurrentUser
) -> FeaturedSlotOut:
    return FeaturedSlotOut.model_validate(
        await service.create_featured(payload, created_by=user.id)
    )


@admin_router.patch("/featured/{slot_id}", response_model=FeaturedSlotOut,
                    dependencies=[_SHOWCASE])
async def update_featured(
    slot_id: int, payload: FeaturedSlotUpdate, service: Service
) -> FeaturedSlotOut:
    return FeaturedSlotOut.model_validate(await service.update_featured(slot_id, payload))


@admin_router.delete("/featured/{slot_id}",
                     status_code=status.HTTP_204_NO_CONTENT,
                     response_class=Response, dependencies=[_SHOWCASE])
async def delete_featured(slot_id: int, service: Service) -> Response:
    await service.delete_featured(slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)