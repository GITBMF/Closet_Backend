"""Geo FastAPI dependencies — wires the service to a request-scoped session."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.geo.repository import GeoRepository
from app.modules.geo.service import GeoService


def get_geo_service(db: Annotated[AsyncSession, Depends(get_db)]) -> GeoService:
    return GeoService(GeoRepository(db))


Service = Annotated[GeoService, Depends(get_geo_service)]