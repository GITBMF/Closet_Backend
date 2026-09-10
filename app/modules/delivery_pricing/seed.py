"""Seed baseline REGION delivery rates so checkout returns an instant total
instead of falling into quote_required.

Runs on startup when SEED_DELIVERY_RATES_ON_STARTUP is enabled. Idempotent:
skips entirely if any delivery rate already exists, so admin-managed rates in
the ops panel are never overwritten. Admins can add per-city rates or adjust
these per-region defaults in the ops panel ("Tarifs de livraison").
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.delivery_pricing.constants import DeliveryScope
from app.modules.delivery_pricing.models import DeliveryRate
from app.modules.delivery_pricing.repository import DeliveryPricingRepository
from app.modules.geo.models import Region

logger = logging.getLogger("closet.delivery_pricing")

# Baseline delivery fee per region, in XAF. Tune anytime in the ops panel.
DEFAULT_FEE = Decimal("2000")
REGION_FEES: dict[str, Decimal] = {
    "Centre": Decimal("1500"),
    "Littoral": Decimal("1500"),
    "Ouest": Decimal("2000"),
    "Sud-Ouest": Decimal("2500"),
    "Nord-Ouest": Decimal("2500"),
    "Sud": Decimal("2500"),
    "Est": Decimal("3000"),
    "Adamaoua": Decimal("3000"),
    "Nord": Decimal("3500"),
    "Extrême-Nord": Decimal("3500"),
}


async def ensure_delivery_rates_seeded() -> None:
    """Insert one REGION rate per region if no rate exists yet."""
    if not getattr(settings, "SEED_DELIVERY_RATES_ON_STARTUP", False):
        return
    created = 0
    try:
        async with AsyncSessionLocal() as session:
            existing = (
                await session.execute(select(func.count()).select_from(DeliveryRate))
            ).scalar_one()
            if existing:
                return
            repo = DeliveryPricingRepository(session)
            regions = (await session.execute(select(Region))).scalars().all()
            for region in regions:
                await repo.create_rate(
                    scope=DeliveryScope.REGION,
                    city_id=None,
                    region_id=region.id,
                    amount=REGION_FEES.get(region.name, DEFAULT_FEE),
                    currency="XAF",
                    created_by=None,
                )
                created += 1
            await session.commit()
    except Exception:  # never let seeding crash startup
        logger.exception("delivery-rate seed: failed; skipping")
        return
    if created:
        logger.info("delivery-rate seed: %d region rate(s) created", created)
