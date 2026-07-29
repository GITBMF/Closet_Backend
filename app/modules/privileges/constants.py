"""Privilege-code enums."""

from __future__ import annotations

from enum import StrEnum


class PrivilegeType(StrEnum):
    PERCENTAGE = "percentage"   # value is a percent (0-100)
    FIXED = "fixed"             # value is an amount in XAF