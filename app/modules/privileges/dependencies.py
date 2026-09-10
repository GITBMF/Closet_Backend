"""Privilege-service dependency wiring."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.privileges.repository import PrivilegeRepository
from app.modules.privileges.service import PrivilegeService


def get_privileges_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrivilegeService:
    return PrivilegeService(PrivilegeRepository(db))


Service = Annotated[PrivilegeService, Depends(get_privileges_service)]
