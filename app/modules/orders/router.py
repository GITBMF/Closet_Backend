"""Order HTTP layer.

  * `router`       -> /orders          checkout (public), tracking, my-orders
  * `admin_router` -> /admin/orders/*  listing, detail, status, manual quote

Checkout is public so guests can buy without an account; if a customer is
logged in, the order is linked to them. Tracking by order number is public
(guests need it) but returns only what's safe to show.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import (
    CurrentUser,
    OptionalUser,
    require_permission,
)
from app.modules.orders.constants import OrderStatus
from app.modules.orders.dependencies import Service
from app.modules.orders.schemas import (
    CheckoutIn,
    ManualQuote,
    OrderOut,
    OrdersPage,
    OrderSummary,
    StatusHistoryOut,
    StatusUpdate,
)

router = APIRouter(prefix="/orders", tags=["orders"])
admin_router = APIRouter(
    prefix="/admin/orders",
    tags=["admin: orders"],
)


# ============================================================ public checkout
@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def checkout(
    payload: CheckoutIn, service: Service, user: OptionalUser
) -> OrderOut:
    order = await service.checkout(payload, user_id=user.id if user else None)
    return OrderOut.model_validate(order)


@router.get("/{order_number}", response_model=OrderOut)
async def track_order(order_number: str, service: Service) -> OrderOut:
    # public tracking by order number (guests need this)
    return OrderOut.model_validate(await service.get_by_number(order_number))


# =============================================================== my orders
@router.get(
    "",
    response_model=OrdersPage,
    dependencies=[Depends(require_permission(Permission.ORDER_READ_OWN))],
)
async def my_orders(
    service: Service,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrdersPage:
    items, total = await service.list_for_user(user.id, limit=limit, offset=offset)
    return OrdersPage(
        items=[OrderSummary.model_validate(o) for o in items],
        total=total, limit=limit, offset=offset,
    )


# ============================================================== admin: orders
@admin_router.get(
    "",
    response_model=OrdersPage,
    dependencies=[Depends(require_permission(Permission.ORDER_READ_ALL))],
)
async def list_orders(
    service: Service,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrdersPage:
    items, total = await service.list_all(
        status=status_filter, limit=limit, offset=offset
    )
    return OrdersPage(
        items=[OrderSummary.model_validate(o) for o in items],
        total=total, limit=limit, offset=offset,
    )


@admin_router.get(
    "/{order_id}",
    response_model=OrderOut,
    dependencies=[Depends(require_permission(Permission.ORDER_READ_ALL))],
)
async def get_order(order_id: uuid.UUID, service: Service) -> OrderOut:
    return OrderOut.model_validate(await service.get_admin(order_id))


@admin_router.get(
    "/{order_id}/history",
    response_model=list[StatusHistoryOut],
    dependencies=[Depends(require_permission(Permission.ORDER_READ_ALL))],
)
async def get_order_history(
    order_id: uuid.UUID, service: Service
) -> list[StatusHistoryOut]:
    entries = await service.get_history(order_id)
    return [StatusHistoryOut.model_validate(e) for e in entries]


@admin_router.patch(
    "/{order_id}/status",
    response_model=OrderOut,
    dependencies=[Depends(require_permission(Permission.ORDER_UPDATE_STATUS))],
)
async def update_status(
    order_id: uuid.UUID, payload: StatusUpdate, service: Service, user: CurrentUser
) -> OrderOut:
    return OrderOut.model_validate(
        await service.update_status(order_id, payload, admin_id=user.id)
    )


@admin_router.post(
    "/{order_id}/quote",
    response_model=OrderOut,
    dependencies=[Depends(require_permission(Permission.ORDER_UPDATE_STATUS))],
)
async def set_manual_quote(
    order_id: uuid.UUID, payload: ManualQuote, service: Service, user: CurrentUser
) -> OrderOut:
    return OrderOut.model_validate(
        await service.set_manual_quote(order_id, payload, admin_id=user.id)
    )