"""Returns enums."""

from __future__ import annotations

from enum import StrEnum


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESOLVED = "resolved"