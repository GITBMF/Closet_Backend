"""Catalogue dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.storage import get_storage
from app.modules.catalogue.repository import CatalogueRepository
from app.modules.catalogue.service import CatalogueService


def get_catalogue_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CatalogueService:
    return CatalogueService(CatalogueRepository(db), storage=get_storage())


Service = Annotated[CatalogueService, Depends(get_catalogue_service)]