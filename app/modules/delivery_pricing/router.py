"""Delivery-pricing HTTP layer.

  * `router`       -> /delivery/quote     public (checkout needs it pre-login)
  * `admin_router` -> /admin/delivery/*   rate management (DELIVERY_RATE_MANAGE)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.modules.delivery_pricing.dependencies import Service
from app.modules.delivery_pricing.schemas import (
    QuoteOut,
    RateCreate,
    RateOut,
    RateUpdate,
)
from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import CurrentUser, require_permission

router = APIRouter(prefix="/delivery", tags=["delivery-pricing"])
admin_router = APIRouter(
    prefix="/admin/delivery",
    tags=["admin: delivery-pricing"],
    dependencies=[Depends(require_permission(Permission.DELIVERY_RATE_MANAGE))],
)


# ------------------------------------------------------------- public quote
@router.get("/quote", response_model=QuoteOut)
async def get_quote(
    service: Service,
    city_id: Annotated[int | None, Query()] = None,
    region_id: Annotated[int | None, Query()] = None,
) -> QuoteOut:
    return await service.quote(city_id=city_id, region_id=region_id)


# ------------------------------------------------------------ admin: rates
@admin_router.get("/rates", response_model=list[RateOut])
async def list_rates(service: Service) -> list[RateOut]:
    return [RateOut.model_validate(r) for r in await service.list_rates()]


@admin_router.post(
    "/rates", response_model=RateOut, status_code=status.HTTP_201_CREATED
)
async def create_rate(
    payload: RateCreate, service: Service, user: CurrentUser
) -> RateOut:
    rate = await service.create_rate(payload, created_by=user.id)
    return RateOut.model_validate(rate)


@admin_router.patch("/rates/{rate_id}", response_model=RateOut)
async def update_rate(
    rate_id: int, payload: RateUpdate, service: Service
) -> RateOut:
    return RateOut.model_validate(await service.update_rate(rate_id, payload))