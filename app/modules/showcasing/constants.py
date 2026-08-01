"""Showcasing enums — must match the DB enum `featured_slot_type`."""

from __future__ import annotations

from enum import StrEnum


class FeaturedSlotType(StrEnum):
    PIECE_OF_THE_WEEK = "piece_of_the_week"
    FAVOURITE = "favourite"
    HERO = "hero"