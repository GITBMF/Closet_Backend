"""Catalogue enums."""

from __future__ import annotations

from enum import StrEnum


class PieceStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RESERVED = "reserved"
    SOLD = "sold"
    WITHDRAWN = "withdrawn"


class PieceCondition(StrEnum):
    NEW = "new"
    VERY_GOOD = "very_good"
    GOOD = "good"


class AcquisitionType(StrEnum):
    DIRECT_BUY = "direct_buy"       # ClosET bought it outright
    CONSIGNMENT = "consignment"     # deposit-sale, sourcer paid on sale


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"