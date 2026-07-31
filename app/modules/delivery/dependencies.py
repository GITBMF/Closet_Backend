"""Delivery dependencies.

The delivery service drives the order forward as a courier reports progress, so
it is built with an OrderService on the SAME request session — the delivery
write and the order transition it triggers commit together.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.delivery.repository import DeliveryRepository
from app.modules.delivery.service import DeliveryService
from app.modules.orders.dependencies import get_order_service


def get_delivery_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeliveryService:
    return DeliveryService(DeliveryRepository(db), get_order_service(db))


Service = Annotated[DeliveryService, Depends(get_delivery_service)]