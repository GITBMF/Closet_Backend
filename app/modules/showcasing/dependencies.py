"""Showcasing dependencies.

The service resolves featured pieces through the catalogue SERVICE, built on the
same request session — so a single request reads sponsors, slots and pieces
consistently.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.catalogue.dependencies import get_catalogue_service
from app.modules.showcasing.repository import ShowcasingRepository
from app.modules.showcasing.service import ShowcasingService


def get_showcasing_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShowcasingService:
    return ShowcasingService(ShowcasingRepository(db), get_catalogue_service(db))


Service = Annotated[ShowcasingService, Depends(get_showcasing_service)]