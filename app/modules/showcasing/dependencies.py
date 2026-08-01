from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.showcasing.repository import ShowcasingRepository
from app.modules.showcasing.service import ShowcasingService
from app.modules.catalogue.repository import CatalogueRepository


def get_showcasing_repository(db: AsyncSession = Depends(get_db)) -> ShowcasingRepository:
    return ShowcasingRepository(db)


def get_showcasing_service(
    repo: ShowcasingRepository = Depends(get_showcasing_repository),
    db: AsyncSession = Depends(get_db)
) -> ShowcasingService:
    catalogue_repo = CatalogueRepository(db)
    return ShowcasingService(repo=repo, catalogue_repo=catalogue_repo)