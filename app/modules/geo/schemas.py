"""Geo API contracts (Pydantic).

Read models for the public reference endpoints, plus small write models for
the admin endpoints that manage delivery zones.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------- reads
class RegionOut(_ORMModel):
    id: int
    name: str
    code: str


class DivisionOut(_ORMModel):
    id: int
    region_id: int
    name: str


class SubdivisionOut(_ORMModel):
    id: int
    division_id: int
    name: str


class CityOut(_ORMModel):
    id: int
    name: str
    region_id: int
    is_active: bool


class NeighbourhoodOut(_ORMModel):
    id: int
    city_id: int
    name: str
    is_active: bool


# -------------------------------------------------------------- writes
class CityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    region_id: int
    is_active: bool = True


class CityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    region_id: int | None = None
    is_active: bool | None = None


class NeighbourhoodCreate(BaseModel):
    city_id: int
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True


class NeighbourhoodUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None