"""Returns repository — return-ticket SQL.

Writes flush but do not commit; the service owns the transaction so a decision
and the cross-module call it triggers (refund / restock) commit together.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.returns.constants import ReturnStatus
from app.modules.returns.models import ReturnTicket

_OPEN = (ReturnStatus.REQUESTED, ReturnStatus.APPROVED)


class ReturnsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, ticket: ReturnTicket) -> ReturnTicket:
        self.db.add(ticket)
        await self.db.flush()
        return ticket

    async def get(self, ticket_id: uuid.UUID) -> ReturnTicket | None:
        return await self.db.get(ReturnTicket, ticket_id)

    async def open_ticket_for(
        self, purchase_id: uuid.UUID, piece_id: uuid.UUID
    ) -> ReturnTicket | None:
        stmt = select(ReturnTicket).where(
            ReturnTicket.purchase_id == purchase_id,
            ReturnTicket.piece_id == piece_id,
            ReturnTicket.status.in_(_OPEN),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ReturnTicket], int]:
        """Tickets on orders owned by this user. Scoped by joining to the
        purchase the ticket references (read-only ownership filter)."""
        from app.modules.orders.models import Purchase

        base = (
            select(ReturnTicket)
            .join(Purchase, Purchase.id == ReturnTicket.purchase_id)
            .where(Purchase.user_id == user_id)
        )
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(ReturnTicket.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def list_all(
        self, *, status: ReturnStatus | None, limit: int, offset: int
    ) -> tuple[list[ReturnTicket], int]:
        base = select(ReturnTicket)
        if status is not None:
            base = base.where(ReturnTicket.status == status)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(ReturnTicket.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def line_price(
        self, purchase_id: uuid.UUID, piece_id: uuid.UUID
    ) -> Decimal | None:
        """The price the customer paid for this piece in this purchase (for the
        default refund amount). None if the piece isn't part of the purchase."""
        from app.modules.orders.models import PurchaseItem

        stmt = select(PurchaseItem.price).where(
            PurchaseItem.purchase_id == purchase_id,
            PurchaseItem.piece_id == piece_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()