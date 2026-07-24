"""Identity repository — the only place identity SQL lives."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.constants import ActorType, UserRole
from app.modules.identity.models import (
    AuditLog,
    DeviceToken,
    PasswordResetToken,
    RefreshToken,
    User,
)


class IdentityRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------ users
    async def get_user(self, user_id: uuid.UUID, *, include_deleted: bool = False) -> User | None:
        stmt = select(User).where(User.id == user_id)
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(
            func.lower(User.email) == email.lower(), User.deleted_at.is_(None)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        stmt = select(func.count()).select_from(User).where(
            func.lower(User.email) == email.lower()
        )
        return bool((await self.db.execute(stmt)).scalar_one())

    async def add_user(self, user: User) -> User:
        self.db.add(user)
        await self.db.flush()
        return user

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        role: UserRole | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[User], int]:
        stmt: Select = select(User).where(User.deleted_at.is_(None))
        if role is not None:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active.is_(is_active))
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.full_name).like(like),
                    func.lower(User.email).like(like),
                    User.phone.like(like),
                )
            )

        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()

        stmt = (
            stmt.order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await self.db.execute(stmt)).scalars().all())
        return rows, int(total)

    # --------------------------------------------------- refresh tokens
    async def add_refresh_token(self, token: RefreshToken) -> RefreshToken:
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_refresh_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return (await self.db.execute(stmt)).unique().scalar_one_or_none()

    async def revoke_family(self, family_id: uuid.UUID) -> int:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        return (await self.db.execute(stmt)).rowcount or 0

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        return (await self.db.execute(stmt)).rowcount or 0

    async def purge_expired_tokens(self) -> int:
        """Housekeeping for the scheduler."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.expires_at < now, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return result.rowcount or 0

    # ------------------------------------------------- one-shot tokens
    async def add_password_reset(self, token: PasswordResetToken) -> PasswordResetToken:
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_password_reset(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def invalidate_password_resets(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )

    # ----------------------------------------------------- device tokens
    async def upsert_device_token(
        self, *, user_id: uuid.UUID, token: str, platform: str, marketing_opt_in: bool
    ) -> DeviceToken:
        existing = (
            await self.db.execute(select(DeviceToken).where(DeviceToken.token == token))
        ).scalar_one_or_none()
        if existing:
            existing.user_id = user_id
            existing.platform = platform
            existing.marketing_opt_in = marketing_opt_in
            existing.last_seen_at = datetime.now(UTC)
            await self.db.flush()
            return existing
        device = DeviceToken(
            user_id=user_id,
            token=token,
            platform=platform,
            marketing_opt_in=marketing_opt_in,
        )
        self.db.add(device)
        await self.db.flush()
        return device

    async def delete_device_token(self, *, user_id: uuid.UUID, token: str) -> bool:
        device = (
            await self.db.execute(
                select(DeviceToken).where(
                    DeviceToken.token == token, DeviceToken.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if not device:
            return False
        await self.db.delete(device)
        return True

    # ------------------------------------------------------- audit log
    async def add_audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: uuid.UUID | None = None,
        payload: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_audit(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        action: str | None = None,
        actor_id: uuid.UUID | None = None,
        entity_type: str | None = None,
    ) -> tuple[list[AuditLog], int]:
        stmt: Select = select(AuditLog)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if actor_id:
            stmt = stmt.where(AuditLog.actor_id == actor_id)
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)

        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        stmt = (
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await self.db.execute(stmt)).scalars().all())
        return rows, int(total)