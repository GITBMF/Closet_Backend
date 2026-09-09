"""Notification HTTP layer — admin template + branding management, dispatch log.

There is no public/customer endpoint here: notifications are sent internally by
other modules calling NotificationService.send(). These routes only let admins
manage templates, edit branding (logo / accent colour), and inspect what went out.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import require_permission
from app.modules.notifications.constants import (
    NotificationChannel,
    NotificationStatus,
)
from app.modules.notifications.dependencies import Service
from app.modules.notifications.schemas import (
    BrandingOut,
    BrandingUpdate,
    NotificationOut,
    NotificationsPage,
    TemplateIn,
    TemplateOut,
    TemplateUpdate,
)

admin_router = APIRouter(
    prefix="/admin/notifications", tags=["admin: notifications"]
)

# no dedicated notification permission exists; admin-level USER_MANAGE gates it.
_MANAGE = Depends(require_permission(Permission.USER_MANAGE))


# ---------------------------------------------------------- templates
@admin_router.post("/templates", response_model=TemplateOut,
                   status_code=status.HTTP_201_CREATED, dependencies=[_MANAGE])
async def create_template(payload: TemplateIn, service: Service) -> TemplateOut:
    return TemplateOut.model_validate(await service.create_template(payload))


@admin_router.get("/templates", response_model=list[TemplateOut], dependencies=[_MANAGE])
async def list_templates(
    service: Service,
    code: Annotated[str | None, Query()] = None,
    channel: Annotated[NotificationChannel | None, Query()] = None,
) -> list[TemplateOut]:
    return [
        TemplateOut.model_validate(t)
        for t in await service.list_templates(code=code, channel=channel)
    ]


@admin_router.patch("/templates/{template_id}", response_model=TemplateOut,
                    dependencies=[_MANAGE])
async def update_template(
    template_id: int, payload: TemplateUpdate, service: Service
) -> TemplateOut:
    return TemplateOut.model_validate(
        await service.update_template(template_id, payload)
    )


# ----------------------------------------------------------- branding
@admin_router.get("/branding", response_model=BrandingOut, dependencies=[_MANAGE])
async def get_branding(service: Service) -> BrandingOut:
    return BrandingOut.model_validate(await service.get_branding())


@admin_router.patch("/branding", response_model=BrandingOut, dependencies=[_MANAGE])
async def update_branding(payload: BrandingUpdate, service: Service) -> BrandingOut:
    return BrandingOut.model_validate(await service.update_branding(payload))


# ------------------------------------------------------- dispatch log
@admin_router.get("", response_model=NotificationsPage, dependencies=[_MANAGE])
async def list_dispatch_log(
    service: Service,
    status_filter: Annotated[NotificationStatus | None, Query(alias="status")] = None,
    channel: Annotated[NotificationChannel | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationsPage:
    items, total = await service.list_notifications(
        status=status_filter, channel=channel, limit=limit, offset=offset
    )
    return NotificationsPage(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total, limit=limit, offset=offset,
    )
