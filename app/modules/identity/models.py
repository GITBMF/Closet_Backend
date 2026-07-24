"""Identity models — the tables this module owns.

users, refresh_tokens, device_tokens, password_reset_tokens, audit_logs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDelete, Timestamped, UUIDPrimaryKey
from app.modules.identity.constants import ActorType, UserRole

# Reuse one PG enum type per Python enum. create_type=False because Alembic
# creates them explicitly in the migration.
user_role_enum = PGEnum(
    UserRole, name="user_role", values_callable=lambda e: [m.value for m in e],
    create_type=False,
)
actor_type_enum = PGEnum(
    ActorType, name="actor_type", values_callable=lambda e: [m.value for m in e],
    create_type=False,
)


class User(UUIDPrimaryKey, Timestamped, SoftDelete, Base):
    __tablename__ = "users"

    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))

    password_hash: Mapped[str | None] = mapped_column(String(255))

    role: Mapped[UserRole] = mapped_column(
        user_role_enum,
        nullable=False,
        default=UserRole.CUSTOMER,
        server_default=UserRole.CUSTOMER.value,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # set on a bootstrap/recovery account: blocks everything except reading
    # your own profile and setting a new password
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    # --- 2FA (mandatory for admins, optional for everyone else) -------
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- brute-force protection ---------------------------------------
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_users_active_role", "role", "is_active"),
    )

    # -- convenience ---------------------------------------------------
    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def mfa_enabled(self) -> bool:
        return self.totp_enabled_at is not None and bool(self.totp_secret)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.id} {self.email or self.phone} {self.role}>"


class RefreshToken(UUIDPrimaryKey, Base):
    """Rotating refresh tokens with reuse detection.

    Only the SHA-256 hash is stored. Rotation links each new token to the one
    it replaced (`parent_id`) and stamps `rotated_at` on the old row; if a
    token that was already rotated is presented again, the whole family is
    revoked — that is the classic stolen-token signal.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )

    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(INET)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens", lazy="joined")

    @property
    def is_usable(self) -> bool:
        from datetime import UTC
        from datetime import datetime as dt

        return (
            self.revoked_at is None
            and self.rotated_at is None
            and self.expires_at > dt.now(UTC)
        )


class DeviceToken(Base):
    """FCM push tokens (transactional push + opt-in marketing)."""

    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    marketing_opt_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordResetToken(UUIDPrimaryKey, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )



class AuditLog(Base):
    """Append-only trail of critical actions (spec section 9).

    BIGINT id + BRIN-friendly created_at so it can become a monthly
    partitioned table later without a schema change.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_type: Mapped[ActorType] = mapped_column(actor_type_enum, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )