"""Returns dependencies.

The returns service issues refunds (payments) and restocks pieces (catalogue) on
the SAME session, so a decision commits atomically with its money/stock effect.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.catalogue.dependencies import get_catalogue_service
from app.modules.orders.dependencies import get_order_service
from app.modules.payments.dependencies import get_payment_service
from app.modules.returns.repository import ReturnsRepository
from app.modules.returns.service import ReturnsService


def get_returns_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReturnsService:
    return ReturnsService(
        ReturnsRepository(db),
        get_order_service(db),
        get_payment_service(db),
        get_catalogue_service(db),
    )


Service = Annotated[ReturnsService, Depends(get_returns_service)]