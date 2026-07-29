"""Order enums."""

from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "pending"            # created, awaiting payment
    PAID = "paid"
    PREPARING = "preparing"
    READY = "ready"               # ready for delivery/pickup
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    QUOTE_REQUIRED = "quote_required"   # out-of-zone: needs a manual fee