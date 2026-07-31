"""Delivery repository — all delivery SQL.

Writes flush but do not commit; the service owns the transaction boundary so a
courier status update AND the order transition it triggers commit together.

The courier link is looked up by the HASH of the incoming token — the raw token
is never stored, so a DB leak yields no working links.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.delivery.constants import DeliveryStatus
from app.modules.delivery.models import (
    Courier,
    CourierAccessLink,
    Delivery,
    DeliveryEvent,
)


class DeliveryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -------------------------------------------------------- couriers
    async def add_courier(self, courier: Courier) -> Courier:
        self.db.add(courier)
        await self.db.flush()
        return courier

    async def get_courier(self, courier_id: uuid.UUID) -> Courier | None:
        return (
            await self.db.execute(select(Courier).where(Courier.id == courier_id))
        ).scalar_one_or_none()

    async def list_couriers(self, *, active_only: bool) -> list[Courier]:
        stmt = select(Courier).order_by(Courier.full_name)
        if active_only:
            stmt = stmt.where(Courier.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    # ------------------------------------------------------ deliveries
    async def add_delivery(self, delivery: Delivery) -> Delivery:
        self.db.add(delivery)
        await self.db.flush()
        return delivery

    async def get(self, delivery_id: uuid.UUID) -> Delivery | None:
        return (
            await self.db.execute(select(Delivery).where(Delivery.id == delivery_id))
        ).scalar_one_or_none()

    async def get_for_purchase(self, purchase_id: uuid.UUID) -> Delivery | None:
        return (
            await self.db.execute(
                select(Delivery).where(Delivery.purchase_id == purchase_id)
            )
        ).scalar_one_or_none()

    async def list_all(
        self, *, status: DeliveryStatus | None, limit: int, offset: int
    ) -> tuple[list[Delivery], int]:
        base = select(Delivery)
        if status is not None:
            base = base.where(Delivery.status == status)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(Delivery.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    # ---------------------------------------------------------- events
    async def add_event(self, event: DeliveryEvent) -> DeliveryEvent:
        self.db.add(event)
        await self.db.flush()
        return event

    async def events_for(self, delivery_id: uuid.UUID) -> list[DeliveryEvent]:
        stmt = (
            select(DeliveryEvent)
            .where(DeliveryEvent.delivery_id == delivery_id)
            .order_by(DeliveryEvent.created_at.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # ----------------------------------------------------------- links
    async def add_link(self, link: CourierAccessLink) -> CourierAccessLink:
        self.db.add(link)
        await self.db.flush()
        return link

    async def get_link_by_hash(self, token_hash: str) -> CourierAccessLink | None:
        return (
            await self.db.execute(
                select(CourierAccessLink).where(
                    CourierAccessLink.token_hash == token_hash
                )
            )
        ).scalar_one_or_none()

    async def get_delivery_with_purchase(self, delivery_id: uuid.UUID):
        """Delivery + its purchase (for the courier view). Returns (delivery,
        purchase) or (None, None)."""
        from app.modules.orders.models import Purchase

        stmt = (
            select(Delivery, Purchase)
            .join(Purchase, Purchase.id == Delivery.purchase_id)
            .where(Delivery.id == delivery_id)
        )
        row = (await self.db.execute(stmt)).first()
        if row is None:
            return None, None
        return row[0], row[1]

    async def count_items(self, purchase_id: uuid.UUID) -> int:
        from app.modules.orders.models import PurchaseItem

        stmt = (
            select(func.count())
            .select_from(PurchaseItem)
            .where(PurchaseItem.purchase_id == purchase_id)
        )
        return int((await self.db.execute(stmt)).scalar_one())