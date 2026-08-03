"""Dashboard dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.service import DashboardService


def get_dashboard_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardService:
    return DashboardService(DashboardRepository(db))


Service = Annotated[DashboardService, Depends(get_dashboard_service)]