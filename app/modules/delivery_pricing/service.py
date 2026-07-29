"""Delivery-pricing service — the quote engine and rate management.

quote(): given a destination, return the fee. Resolution order:
  1. a current rate for the exact fixed-rate city
  2. else a current rate for the region
  3. else quote_required=True (out-of-zone; the admin sets a manual fee on
     the order)

Creating a rate for a target that already has a current one supersedes the
old rate (stamps its effective_to) rather than leaving two active — so there
is always at most one current rate per target, and the history stays intact.

Other modules (orders) call quote() through this service, never the repo.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.delivery_pricing.constants import DeliveryScope
from app.modules.delivery_pricing.models import DeliveryRate
from app.modules.delivery_pricing.repository import DeliveryPricingRepository
from app.modules.delivery_pricing.schemas import QuoteOut, RateCreate, RateUpdate
from app.modules.geo.repository import GeoRepository


class DeliveryPricingService:
    def __init__(
        self, repo: DeliveryPricingRepository, geo: GeoRepository
    ) -> None:
        self.repo = repo
        self.geo = geo

    # ------------------------------------------------------------ quote
    async def quote(
        self, *, city_id: int | None, region_id: int | None
    ) -> QuoteOut:
        if city_id is None and region_id is None:
            raise ValidationError(
                "Fournissez city_id ou region_id.", code="destination_required"
            )

        # 1. exact city rate
        if city_id is not None:
            city = await self.geo.get_city(city_id)
            if city is None:
                raise NotFoundError("Ville introuvable.", code="city_not_found")
            rate = await self.repo.current_city_rate(city_id)
            if rate is not None:
                return QuoteOut(
                    scope=DeliveryScope.CITY,
                    amount=rate.amount,
                    currency=rate.currency,
                    city_id=city_id,
                )
            # 2. fall back to the city's region
            region_id = region_id or city.region_id

        # 2/3. region rate, else quote-required
        if region_id is not None:
            rate = await self.repo.current_region_rate(region_id)
            if rate is not None:
                return QuoteOut(
                    scope=DeliveryScope.REGION,
                    amount=rate.amount,
                    currency=rate.currency,
                    region_id=region_id,
                )

        # 3. nothing covers it — the order will need a manual quote
        return QuoteOut(
            scope=DeliveryScope.REGION,
            amount=0,
            currency="XAF",
            city_id=city_id,
            region_id=region_id,
            quote_required=True,
        )

    # ------------------------------------------------------------ reads
    async def list_rates(self) -> list[DeliveryRate]:
        return await self.repo.list_current()

    # ----------------------------------------------------------- writes
    async def create_rate(
        self, payload: RateCreate, *, created_by: uuid.UUID | None
    ) -> DeliveryRate:
        # validate the target exists
        if payload.scope is DeliveryScope.CITY:
            if await self.geo.get_city(payload.city_id) is None:
                raise NotFoundError("Ville introuvable.", code="city_not_found")
        else:
            if await self.geo.get_region(payload.region_id) is None:
                raise NotFoundError("Région introuvable.", code="region_not_found")

        now = datetime.now(UTC)
        # supersede an existing current rate for the same target
        existing = await self.repo.find_current_for_target(
            payload.scope, city_id=payload.city_id, region_id=payload.region_id
        )
        if existing is not None:
            await self.repo.supersede(existing, at=now)

        rate = await self.repo.create_rate(
            scope=payload.scope,
            city_id=payload.city_id,
            region_id=payload.region_id,
            amount=payload.amount,
            currency=payload.currency,
            created_by=created_by,
        )
        await self.repo.db.commit()
        await self.repo.db.refresh(rate)
        return rate

    async def update_rate(self, rate_id: int, payload: RateUpdate) -> DeliveryRate:
        rate = await self.repo.get(rate_id)
        if rate is None:
            raise NotFoundError("Tarif introuvable.", code="rate_not_found")
        rate.amount = payload.amount
        await self.repo.db.commit()
        await self.repo.db.refresh(rate)
        return rate