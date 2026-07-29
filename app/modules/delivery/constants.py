"""Delivery-execution enums."""

from __future__ import annotations

from enum import StrEnum


class DeliveryStatus(StrEnum):
    ASSIGNED = "assigned"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"