"""Order dependencies.

The order service orchestrates catalogue and delivery-pricing, so it is
constructed with all three services sharing one request session — checkout
reserves pieces and reads a quote inside the same transaction it writes the
order in.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.storage import get_storage
from app.modules.catalogue.repository import CatalogueRepository
from app.modules.catalogue.service import CatalogueService
from app.modules.delivery_pricing.repository import DeliveryPricingRepository
from app.modules.delivery_pricing.service import DeliveryPricingService
from app.modules.geo.repository import GeoRepository
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService


def get_order_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrderService:
    catalogue = CatalogueService(CatalogueRepository(db), storage=get_storage())
    pricing = DeliveryPricingService(
        DeliveryPricingRepository(db), GeoRepository(db)
    )
    return OrderService(OrderRepository(db), catalogue, pricing)


Service = Annotated[OrderService, Depends(get_order_service)]