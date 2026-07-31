"""Payment repository — all payment SQL.

Writes flush but do not commit; the service owns the transaction boundary so a
webhook that confirms a payment AND flips the order to paid commits atomically.
The two idempotency guarantees live here as lookups:
  * get_by_idempotency_key — don't create a second payment for the same attempt
  * event_exists           — don't process the same provider callback twice
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.constants import PaymentStatus
from app.modules.payments.models import (
    Payment,
    PaymentEvent,
    PaymentProvider,
    Refund,
)


class PaymentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----------------------------------------------------------- providers
    async def get_provider_by_code(self, code: str) -> PaymentProvider | None:
        stmt = select(PaymentProvider).where(PaymentProvider.code == code)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def ensure_provider(self, code: str, name: str) -> PaymentProvider:
        existing = await self.get_provider_by_code(code)
        if existing is not None:
            return existing
        provider = PaymentProvider(code=code, name=name)
        self.db.add(provider)
        await self.db.flush()
        return provider

    # ------------------------------------------------------------ payments
    async def add_payment(self, payment: Payment) -> Payment:
        self.db.add(payment)
        await self.db.flush()
        return payment

    async def get(self, payment_id: uuid.UUID) -> Payment | None:
        return (
            await self.db.execute(select(Payment).where(Payment.id == payment_id))
        ).scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        return (
            await self.db.execute(
                select(Payment).where(Payment.idempotency_key == key)
            )
        ).scalar_one_or_none()

    async def get_by_provider_reference(self, ref: str) -> Payment | None:
        return (
            await self.db.execute(
                select(Payment).where(Payment.provider_reference == ref)
            )
        ).scalar_one_or_none()

    async def latest_for_purchase(self, purchase_id: uuid.UUID) -> Payment | None:
        stmt = (
            select(Payment)
            .where(Payment.purchase_id == purchase_id)
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_all(
        self,
        *,
        status: PaymentStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Payment], int]:
        base = select(Payment)
        if status is not None:
            base = base.where(Payment.status == status)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(Payment.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    # -------------------------------------------------------------- events
    async def event_exists(self, provider_event_id: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(PaymentEvent)
            .where(PaymentEvent.provider_event_id == provider_event_id)
        )
        return bool((await self.db.execute(stmt)).scalar_one())

    async def add_event(self, event: PaymentEvent) -> PaymentEvent:
        self.db.add(event)
        await self.db.flush()
        return event

    # ------------------------------------------------------------- refunds
    async def add_refund(self, refund: Refund) -> Refund:
        self.db.add(refund)
        await self.db.flush()
        return refund

    async def total_refunded(self, payment_id: uuid.UUID):
        stmt = (
            select(func.coalesce(func.sum(Refund.amount), 0))
            .where(Refund.payment_id == payment_id)
        )
        return (await self.db.execute(stmt)).scalar_one()