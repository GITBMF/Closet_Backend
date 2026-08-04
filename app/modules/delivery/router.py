"""Delivery HTTP layer.

  * admin_router -> /admin/deliveries/*   create, assign, link, status, events
  * courier_router -> /courier/*          the account-less courier link (7.3)

The courier endpoints carry NO JWT. The token in the path IS the credential —
the service hashes it, checks expiry/revoke/uses, and refuses otherwise.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.config import settings
from app.modules.delivery.constants import DeliveryStatus
from app.modules.delivery.dependencies import Service
from app.modules.delivery.schemas import (
    AdminStatusIn,
    AssignIn,
    CourierDeliveryView,
    CourierIn,
    CourierOut,
    CourierStatusIn,
    CreateDeliveryIn,
    DeliveriesPage,
    DeliveryOut,
    DeliverySummary,
    EventOut,
    LinkIn,
    LinkOut,
)
from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import CurrentUser, require_permission

admin_router = APIRouter(prefix="/admin/deliveries", tags=["admin: deliveries"])
courier_router = APIRouter(prefix="/courier", tags=["courier"])

_MANAGE = Depends(require_permission(Permission.DELIVERY_MANAGE))


# ============================================================ admin: couriers
@admin_router.post("/couriers", response_model=CourierOut,
                   status_code=status.HTTP_201_CREATED, dependencies=[_MANAGE])
async def create_courier(payload: CourierIn, service: Service) -> CourierOut:
    return CourierOut.model_validate(await service.create_courier(payload))


@admin_router.get("/couriers", response_model=list[CourierOut], dependencies=[_MANAGE])
async def list_couriers(
    service: Service,
    active_only: Annotated[bool, Query()] = False,
) -> list[CourierOut]:
    return [CourierOut.model_validate(c) for c in await service.list_couriers(active_only=active_only)]


# ========================================================= admin: deliveries
@admin_router.get("", response_model=DeliveriesPage, dependencies=[_MANAGE])
async def list_deliveries(
    service: Service,
    status_filter: Annotated[DeliveryStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DeliveriesPage:
    items, total = await service.list_all(status=status_filter, limit=limit, offset=offset)
    return DeliveriesPage(
        items=[DeliverySummary.model_validate(d) for d in items],
        total=total, limit=limit, offset=offset,
    )


@admin_router.post("", response_model=DeliveryOut,
                   status_code=status.HTTP_201_CREATED, dependencies=[_MANAGE])
async def create_delivery(payload: CreateDeliveryIn, service: Service) -> DeliveryOut:
    return DeliveryOut.model_validate(await service.create_delivery(payload))


@admin_router.get("/{delivery_id}", response_model=DeliveryOut, dependencies=[_MANAGE])
async def get_delivery(delivery_id: uuid.UUID, service: Service) -> DeliveryOut:
    return DeliveryOut.model_validate(await service.get(delivery_id))


@admin_router.patch("/{delivery_id}/assign", response_model=DeliveryOut, dependencies=[_MANAGE])
async def assign_courier(delivery_id: uuid.UUID, payload: AssignIn, service: Service) -> DeliveryOut:
    return DeliveryOut.model_validate(await service.assign(delivery_id, payload))


@admin_router.patch("/{delivery_id}/status", response_model=DeliveryOut, dependencies=[_MANAGE])
async def admin_update_status(
    delivery_id: uuid.UUID, payload: AdminStatusIn, service: Service, user: CurrentUser
) -> DeliveryOut:
    return DeliveryOut.model_validate(
        await service.admin_update_status(delivery_id, payload, admin_id=user.id)
    )


@admin_router.get("/{delivery_id}/events", response_model=list[EventOut], dependencies=[_MANAGE])
async def delivery_events(delivery_id: uuid.UUID, service: Service) -> list[EventOut]:
    return [EventOut.model_validate(e) for e in await service.events(delivery_id)]


@admin_router.post("/{delivery_id}/link", response_model=LinkOut,
                   status_code=status.HTTP_201_CREATED, dependencies=[_MANAGE])
async def create_courier_link(
    delivery_id: uuid.UUID, payload: LinkIn, service: Service
) -> LinkOut:
    link, raw_token = await service.generate_link(delivery_id, payload)
    # the RAW token is surfaced exactly here, once — never stored, never returned again
    return LinkOut(
        id=link.id,
        delivery_id=link.delivery_id,
        token=raw_token,
        expires_at=link.expires_at,
        max_uses=link.max_uses,
    )


# =============================================== courier (account-less link)
@courier_router.get("/{token}", response_model=CourierDeliveryView)
async def courier_see_delivery(token: str, service: Service) -> CourierDeliveryView:
    return await service.courier_view(token)


@courier_router.post("/{token}/status", response_model=CourierDeliveryView)
async def courier_update_status(
    token: str, payload: CourierStatusIn, service: Service
) -> CourierDeliveryView:
    return await service.courier_update_status(token, payload)