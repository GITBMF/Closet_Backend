"""Data access for privilege (discount / promo) codes and their redemptions."""
from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.privileges.models import PrivilegeCode, PrivilegeRedemption


class PrivilegeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_code(self, code: str) -> PrivilegeCode | None:
        return (
            await self.db.execute(
                select(PrivilegeCode).where(PrivilegeCode.code == code)
            )
        ).scalar_one_or_none()

    async def get(self, code_id: uuid.UUID) -> PrivilegeCode | None:
        return await self.db.get(PrivilegeCode, code_id)

    async def list_codes(self) -> list[PrivilegeCode]:
        return list(
            (
                await self.db.execute(
                    select(PrivilegeCode).order_by(PrivilegeCode.created_at.desc())
                )
            ).scalars().all()
        )

    async def add(self, code: PrivilegeCode) -> PrivilegeCode:
        self.db.add(code)
        await self.db.flush()
        return code

    async def add_redemption(self, redemption: PrivilegeRedemption) -> None:
        self.db.add(redemption)
        await self.db.flush()

    async def increment_usage(self, code_id: uuid.UUID) -> None:
        # Atomic increment so concurrent checkouts can't under-count usage.
        await self.db.execute(
            update(PrivilegeCode)
            .where(PrivilegeCode.id == code_id)
            .values(times_used=PrivilegeCode.times_used + 1)
        )
