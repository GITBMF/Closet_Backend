"""Pydantic contracts for the identity module."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import settings
from app.modules.identity.constants import UserRole

PHONE_RE = re.compile(r"^\+?[0-9]{8,15}$")


def _validate_password(v: str) -> str:
    if len(v) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Le mot de passe doit contenir au moins {settings.PASSWORD_MIN_LENGTH} caractères."
        )
    if len(v.encode("utf-8")) > 72:
        raise ValueError("Mot de passe trop long (72 octets maximum).")
    if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
        raise ValueError("Le mot de passe doit contenir des lettres et des chiffres.")
    return v


Password = Annotated[str, Field(min_length=1, max_length=128)]


# ------------------------------------------------------------------ input
class RegisterRequest(BaseModel):
    email: EmailStr
    password: Password
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=100)

    _pw = field_validator("password")(_validate_password)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str | None) -> str | None:
        if v and not PHONE_RE.match(v.replace(" ", "")):
            raise ValueError("Numéro de téléphone invalide (format E.164 attendu).")
        return v.replace(" ", "") if v else v


class LoginRequest(BaseModel):
    email: EmailStr
    password: Password


class MFAChallengeRequest(BaseModel):
    challenge_token: str
    code: str = Field(min_length=6, max_length=10)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None
    all_devices: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: Password
    new_password: Password

    _pw = field_validator("new_password")(_validate_password)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: Password

    _pw = field_validator("new_password")(_validate_password)


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=100)
    # Changing the login address requires the current password: it is the
    # account's identifier, and there is no e-mail verification in this
    # version to catch a typo.
    email: EmailStr | None = None
    current_password: Password | None = None

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: str | None) -> str | None:
        if v and not PHONE_RE.match(v.replace(" ", "")):
            raise ValueError("Numéro de téléphone invalide.")
        return v.replace(" ", "") if v else v


class RegisterDeviceRequest(BaseModel):
    token: str = Field(min_length=10, max_length=255)
    platform: str = Field(pattern="^(android|ios)$")
    marketing_opt_in: bool = False


class MFAVerifySetupRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class MFADisableRequest(BaseModel):
    password: Password
    code: str = Field(min_length=6, max_length=10)


# --- admin ----------------------------------------------------------------
class AdminUpdateUserRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = None
    city: str | None = None
    is_active: bool | None = None


class AdminChangeRoleRequest(BaseModel):
    role: UserRole
    reason: str | None = Field(default=None, max_length=255)


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    role: UserRole = UserRole.CUSTOMER
    phone: str | None = None
    password: Password | None = None

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str | None) -> str | None:
        return _validate_password(v) if v else v


# ----------------------------------------------------------------- output
class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    full_name: str
    phone: str | None
    city: str | None
    role: UserRole
    is_active: bool
    mfa_enabled: bool = False
    must_change_password: bool = False
    created_at: datetime
    last_login_at: datetime | None = None

    @classmethod
    def from_user(cls, user) -> UserPublic:
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            city=user.city,
            role=user.role,
            is_active=user.is_active,
            mfa_enabled=user.mfa_enabled,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class MeResponse(UserPublic):
    permissions: list[str] = Field(default_factory=list)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class MFARequired(BaseModel):
    mfa_required: bool = True
    challenge_token: str
    expires_in: int


class MFASetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    recovery_codes: list[str]


class MessageResponse(BaseModel):
    message: str


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class UserPage(BaseModel):
    items: list[UserPublic]
    meta: PageMeta


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_type: str
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    ip_address: str | None
    created_at: datetime

    @field_validator("ip_address", "actor_type", mode="before")
    @classmethod
    def _stringify(cls, v):
        # INET columns come back as IPv4Address/IPv6Address; enums as StrEnum.
        return str(v) if v is not None else None


class AuditPage(BaseModel):
    items: list[AuditEntry]
    meta: PageMeta