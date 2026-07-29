"""Payment enums."""

from __future__ import annotations

from enum import StrEnum


class PaymentStatus(StrEnum):
    INITIATED = "initiated"
    PENDING = "pending"       # awaiting provider confirmation
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"