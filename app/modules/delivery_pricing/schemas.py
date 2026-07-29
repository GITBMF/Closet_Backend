"""Delivery-pricing API contracts.

A public quote endpoint (the customer app calls it at checkout) and admin
endpoints to manage the rate table.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.delivery_pricing.constants import DeliveryScope


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------- quote
class QuoteOut(BaseModel):
    """The fee for a destination, plus how it was resolved."""

    scope: DeliveryScope
    amount: Decimal
    currency: str
    city_id: int | None = None
    region_id: int | None = None
    quote_required: bool = False   # true when no rate covers the destination


# --------------------------------------------------------------- reads
class RateOut(_ORMModel):
    id: int
    scope: DeliveryScope
    city_id: int | None
    region_id: int | None
    amount: Decimal
    currency: str
    effective_from: datetime
    effective_to: datetime | None


# -------------------------------------------------------------- writes
class RateCreate(BaseModel):
    scope: DeliveryScope
    city_id: int | None = None
    region_id: int | None = None
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="XAF", min_length=3, max_length=3)

    @model_validator(mode="after")
    def _one_target(self) -> RateCreate:
        # a CITY rate targets a city; a REGION rate targets a region — exactly one
        if self.scope is DeliveryScope.CITY and (
            self.city_id is None or self.region_id is not None
        ):
            raise ValueError("A city rate needs city_id and no region_id.")
        if self.scope is DeliveryScope.REGION and (
            self.region_id is None or self.city_id is not None
        ):
            raise ValueError("A region rate needs region_id and no city_id.")
        return self


class RateUpdate(BaseModel):
    """Only the amount can be edited in place; scope/target are immutable.

    A different target is a different rate — create a new one instead.
    """

    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)