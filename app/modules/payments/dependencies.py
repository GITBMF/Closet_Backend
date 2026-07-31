"""Payment dependencies.

The payment service drives orders on a confirmed webhook, so it is built with
an OrderService on the SAME request session — a webhook that marks a payment
succeeded and flips the order to paid commits as one transaction. The active
provider comes from config via the registry.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.orders.dependencies import get_order_service
from app.modules.payments.providers.registry import get_provider
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.service import PaymentService


def get_payment_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentService:
    orders = get_order_service(db)
    return PaymentService(
        PaymentRepository(db),
        orders,
        get_provider(),
        currency=settings.PAYMENTS_CURRENCY,
        return_url=settings.PAYMENTS_RETURN_URL,
        notify_url=settings.CINETPAY_NOTIFY_URL,
    )


Service = Annotated[PaymentService, Depends(get_payment_service)]