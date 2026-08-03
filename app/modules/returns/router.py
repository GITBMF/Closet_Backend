"""Returns HTTP layer.

  * router       -> /returns/*         customer (own orders, JWT)
  * admin_router -> /admin/returns/*   review + decisions (return:manage)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import CurrentUser, require_permission
from app.modules.returns.constants import ReturnStatus
from app.modules.returns.dependencies import Service
from app.modules.returns.schemas import (
    ApproveIn,
    RejectIn,
    ResolveIn,
    ReturnCreate,
    ReturnOut,
    ReturnsPage,
)

router = APIRouter(prefix="/returns", tags=["returns"])
admin_router = APIRouter(prefix="/admin/returns", tags=["admin: returns"])

_MANAGE = Depends(require_permission(Permission.RETURN_MANAGE))


def _page(items, total, limit, offset) -> ReturnsPage:
    return ReturnsPage(
        items=[ReturnOut.model_validate(t) for t in items],
        total=total, limit=limit, offset=offset,
    )


# ================================================= customer (own orders)
@router.post("", response_model=ReturnOut, status_code=status.HTTP_201_CREATED)
async def request_return(
    payload: ReturnCreate, service: Service, user: CurrentUser
) -> ReturnOut:
    return ReturnOut.model_validate(await service.request_return(user.id, payload))


@router.get("", response_model=ReturnsPage)
async def my_returns(
    service: Service, user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReturnsPage:
    items, total = await service.my_returns(user.id, limit=limit, offset=offset)
    return _page(items, total, limit, offset)


@router.get("/{ticket_id}", response_model=ReturnOut)
async def my_return(
    ticket_id: uuid.UUID, service: Service, user: CurrentUser
) -> ReturnOut:
    return ReturnOut.model_validate(await service.my_return(user.id, ticket_id))


# ===================================================== admin (return:manage)
@admin_router.get("", response_model=ReturnsPage, dependencies=[_MANAGE])
async def list_returns(
    service: Service,
    status_filter: Annotated[ReturnStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReturnsPage:
    items, total = await service.list_all(status=status_filter, limit=limit, offset=offset)
    return _page(items, total, limit, offset)


@admin_router.get("/{ticket_id}", response_model=ReturnOut, dependencies=[_MANAGE])
async def get_return(ticket_id: uuid.UUID, service: Service) -> ReturnOut:
    return ReturnOut.model_validate(await service.get(ticket_id))


@admin_router.post("/{ticket_id}/approve", response_model=ReturnOut, dependencies=[_MANAGE])
async def approve_return(
    ticket_id: uuid.UUID, payload: ApproveIn, service: Service, user: CurrentUser
) -> ReturnOut:
    return ReturnOut.model_validate(
        await service.approve(ticket_id, payload, admin_id=user.id)
    )


@admin_router.post("/{ticket_id}/reject", response_model=ReturnOut, dependencies=[_MANAGE])
async def reject_return(
    ticket_id: uuid.UUID, payload: RejectIn, service: Service, user: CurrentUser
) -> ReturnOut:
    return ReturnOut.model_validate(
        await service.reject(ticket_id, payload, admin_id=user.id)
    )


@admin_router.post("/{ticket_id}/resolve", response_model=ReturnOut, dependencies=[_MANAGE])
async def resolve_return(
    ticket_id: uuid.UUID, payload: ResolveIn, service: Service, user: CurrentUser
) -> ReturnOut:
    return ReturnOut.model_validate(
        await service.resolve(ticket_id, payload, admin_id=user.id)
    )