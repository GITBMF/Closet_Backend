"""Dashboard repository — thin, read-only SELECTs over the dashboard views.

Every query targets a v_dashboard_* view (created in migration 0004). No table
is touched and nothing is written, so this module never conflicts with any
other. The aggregation lives in the views; this layer only reads and shapes.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DashboardRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def overview(self) -> dict:
        row = (await self.db.execute(text("SELECT * FROM v_dashboard_overview"))).mappings().first()
        return dict(row) if row else {}

    async def sales_daily(
        self, *, start: date | None, end: date | None
    ) -> list[dict]:
        clauses = []
        params: dict = {}
        if start is not None:
            clauses.append("day >= :start")
            params["start"] = start
        if end is not None:
            clauses.append("day <= :end")
            params["end"] = end
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT day, orders, revenue FROM v_dashboard_sales_daily{where} ORDER BY day"
        rows = (await self.db.execute(text(sql), params)).mappings().all()
        return [dict(r) for r in rows]

    async def sourcer_balances(self, *, limit: int, offset: int) -> list[dict]:
        rows = (
            await self.db.execute(
                text(
                    "SELECT sourcer_id, display_name, status, amount_outstanding, "
                    "amount_paid, payouts_open FROM v_dashboard_sourcer_balances "
                    "ORDER BY amount_outstanding DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    async def unsold_pieces(self, *, limit: int) -> list[dict]:
        rows = (
            await self.db.execute(
                text(
                    "SELECT piece_id, title, price, created_at, "
                    "EXTRACT(DAY FROM age)::int AS age_days "
                    "FROM v_dashboard_unsold_pieces LIMIT :limit"
                ),
                {"limit": limit},
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    async def overdue_orders(self, *, limit: int) -> list[dict]:
        rows = (
            await self.db.execute(
                text(
                    "SELECT purchase_id, order_number, status, total, placed_at, "
                    "EXTRACT(DAY FROM age)::int AS age_days "
                    "FROM v_dashboard_overdue_orders LIMIT :limit"
                ),
                {"limit": limit},
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    async def unsold_count(self) -> int:
        return (
            await self.db.execute(text("SELECT COUNT(*) FROM v_dashboard_unsold_pieces"))
        ).scalar_one()

    async def overdue_count(self) -> int:
        return (
            await self.db.execute(text("SELECT COUNT(*) FROM v_dashboard_overdue_orders"))
        ).scalar_one()