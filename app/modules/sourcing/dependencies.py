"""Sourcing dependencies.

The sourcing service calls identity (grant role) and catalogue (create piece)
on the SAME session, so an approval or a catalogue action commits atomically
with the sourcing write.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.catalogue.dependencies import get_catalogue_service
from app.modules.identity.dependencies import get_identity_service
from app.modules.sourcing.repository import SourcingRepository
from app.modules.sourcing.service import SourcingService


def get_sourcing_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SourcingService:
    return SourcingService(
        SourcingRepository(db),
        get_identity_service(db),
        get_catalogue_service(db),
    )


Service = Annotated[SourcingService, Depends(get_sourcing_service)]