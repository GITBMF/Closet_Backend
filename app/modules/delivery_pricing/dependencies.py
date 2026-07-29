"""Delivery-pricing dependencies.

The service needs geo's repository too (to validate targets and resolve a
city's region), so it's constructed with both repositories on the same
request session.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.delivery_pricing.repository import DeliveryPricingRepository
from app.modules.delivery_pricing.service import DeliveryPricingService
from app.modules.geo.repository import GeoRepository


def get_pricing_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeliveryPricingService:
    return DeliveryPricingService(DeliveryPricingRepository(db), GeoRepository(db))


Service = Annotated[DeliveryPricingService, Depends(get_pricing_service)]