"""Delivery-execution enums and state rules."""

from __future__ import annotations

from enum import StrEnum


class DeliveryStatus(StrEnum):
    ASSIGNED = "assigned"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"


# Allowed delivery status transitions. A failed delivery can be retried by
# reassigning (admin) which puts it back to ASSIGNED.
DELIVERY_TRANSITIONS: dict[DeliveryStatus, set[DeliveryStatus]] = {
    DeliveryStatus.ASSIGNED: {DeliveryStatus.PICKED_UP, DeliveryStatus.FAILED},
    DeliveryStatus.PICKED_UP: {DeliveryStatus.IN_TRANSIT, DeliveryStatus.DELIVERED, DeliveryStatus.FAILED},
    DeliveryStatus.IN_TRANSIT: {DeliveryStatus.DELIVERED, DeliveryStatus.FAILED},
    DeliveryStatus.DELIVERED: set(),
    DeliveryStatus.FAILED: {DeliveryStatus.ASSIGNED},   # reassign to retry
}

# event source tags
SOURCE_ADMIN = "admin"
SOURCE_COURIER = "courier_link"
SOURCE_SYSTEM = "system"