"""Sourcing enums."""

from __future__ import annotations

from enum import StrEnum


class SourcerStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class CollaborationType(StrEnum):
    DIRECT_SALE = "direct_sale"     # ClosET buys outright
    CONSIGNMENT = "consignment"     # deposit-sale


class SubmissionStatus(StrEnum):
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    REFUSED = "refused"
    CATALOGUED = "catalogued"       # turned into a piece


class PayoutStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    FAILED = "failed"


class EntrustStatus(StrEnum):
    REQUESTED = "requested"
    RETURNED = "returned"           # item given back to sourcer (unsold)
    SETTLED = "settled"             # paid out after sale


class CollectionMethod(StrEnum):
    DROP_OFF = "drop_off"
    PICKUP = "pickup"