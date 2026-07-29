"""Delivery-pricing enums."""

from __future__ import annotations

from enum import StrEnum


class DeliveryScope(StrEnum):
    CITY = "city"       # flat rate for a fixed-rate city
    REGION = "region"   # out-of-zone, per-region rate