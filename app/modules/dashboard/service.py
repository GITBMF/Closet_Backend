"""Dashboard service — assembles read-only KPI responses from the views.

Pure reads; no writes, no cross-module service calls. The heavy lifting is in
the SQL views, so this layer just maps rows onto the response schemas and adds a
couple of derived totals.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.schemas import (
    Alerts,
    OverdueOrder,
    Overview,
    SalesPoint,
    SalesSeries,
    SourcerBalance,
    UnsoldPiece,
)


class DashboardService:
    def __init__(self, repo: DashboardRepository) -> None:
        self.repo = repo

    async def overview(self) -> Overview:
        data = await self.repo.overview()
        return Overview(**data)

    async def sales(self, *, start: date | None, end: date | None) -> SalesSeries:
        rows = await self.repo.sales_daily(start=start, end=end)
        points = [SalesPoint(**r) for r in rows]
        return SalesSeries(
            points=points,
            total_orders=sum(p.orders for p in points),
            total_revenue=sum((p.revenue for p in points), Decimal("0")),
        )

    async def sourcer_balances(
        self, *, limit: int, offset: int
    ) -> list[SourcerBalance]:
        rows = await self.repo.sourcer_balances(limit=limit, offset=offset)
        return [SourcerBalance(**r) for r in rows]

    async def alerts(self, *, limit: int) -> Alerts:
        unsold = await self.repo.unsold_pieces(limit=limit)
        overdue = await self.repo.overdue_orders(limit=limit)
        return Alerts(
            unsold_pieces=[UnsoldPiece(**r) for r in unsold],
            overdue_orders=[OverdueOrder(**r) for r in overdue],
            unsold_count=await self.repo.unsold_count(),
            overdue_count=await self.repo.overdue_count(),
        )