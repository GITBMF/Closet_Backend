"""Dashboard HTTP layer — admin KPI endpoints (read-only).

All routes are gated by dashboard:read. Read-only over the v_dashboard_* views;
no writes anywhere, so this module never conflicts with the others.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.dashboard.dependencies import Service
from app.modules.dashboard.schemas import (
    Alerts,
    Overview,
    SalesSeries,
    SourcerBalance,
)
from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import require_permission

admin_router = APIRouter(prefix="/admin/dashboard", tags=["admin: dashboard"])

_READ = Depends(require_permission(Permission.DASHBOARD_READ))


@admin_router.get("/overview", response_model=Overview, dependencies=[_READ])
async def overview(service: Service) -> Overview:
    return await service.overview()


@admin_router.get("/sales", response_model=SalesSeries, dependencies=[_READ])
async def sales(
    service: Service,
    start: Annotated[date | None, Query(description="inclusive start day")] = None,
    end: Annotated[date | None, Query(description="inclusive end day")] = None,
) -> SalesSeries:
    return await service.sales(start=start, end=end)


@admin_router.get("/sourcers", response_model=list[SourcerBalance], dependencies=[_READ])
async def sourcers(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SourcerBalance]:
    return await service.sourcer_balances(limit=limit, offset=offset)


@admin_router.get("/alerts", response_model=Alerts, dependencies=[_READ])
async def alerts(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Alerts:
    return await service.alerts(limit=limit)