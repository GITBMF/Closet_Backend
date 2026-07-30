"""Order repository — all order SQL.

Reads eager-load items where the caller needs them. Writes flush but do not
commit; the service owns the transaction boundary (checkout must be atomic
across several tables plus cross-module reservations).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.orders.constants import OrderStatus
from app.modules.orders.models import (
    Purchase,
    PurchaseItem,
    PurchaseStatusHistory,
)


class OrderRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------- creates
    async def add_purchase(self, purchase: Purchase) -> Purchase:
        self.db.add(purchase)
        await self.db.flush()
        return purchase

    async def add_item(self, item: PurchaseItem) -> PurchaseItem:
        self.db.add(item)
        await self.db.flush()
        return item

    async def add_history(self, entry: PurchaseStatusHistory) -> None:
        self.db.add(entry)
        await self.db.flush()

    async def history_for(
        self, purchase_id: uuid.UUID
    ) -> list[PurchaseStatusHistory]:
        stmt = (
            select(PurchaseStatusHistory)
            .where(PurchaseStatusHistory.purchase_id == purchase_id)
            .order_by(PurchaseStatusHistory.created_at, PurchaseStatusHistory.id)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # --------------------------------------------------------------- reads
    async def get(
        self, purchase_id: uuid.UUID, *, with_items: bool = False
    ) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.id == purchase_id)
        if with_items:
            stmt = stmt.options(selectinload(Purchase.items))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_number(
        self, order_number: str, *, with_items: bool = False
    ) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.order_number == order_number)
        if with_items:
            stmt = stmt.options(selectinload(Purchase.items))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def order_number_exists(self, order_number: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(Purchase)
            .where(Purchase.order_number == order_number)
        )
        return bool((await self.db.execute(stmt)).scalar_one())

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[Purchase], int]:
        base = select(Purchase).where(Purchase.user_id == user_id)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(Purchase.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def list_all(
        self,
        *,
        status: OrderStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Purchase], int]:
        base = select(Purchase)
        if status is not None:
            base = base.where(Purchase.status == status)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(Purchase.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)