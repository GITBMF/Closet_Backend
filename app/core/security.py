"""Security primitives: password hashing, JWT, TOTP, opaque tokens.

No business logic here — this module only knows how to hash, sign and verify.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.modules.identity.constants import TokenType

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ----------------------------------------------------------------- passwords
def hash_password(plain: str) -> str:
    # bcrypt silently truncates beyond 72 bytes; reject instead of surprising
    if len(plain.encode("utf-8")) > 72:
        raise ValueError("password too long (max 72 bytes)")
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _pwd_context.verify(plain, hashed)
    except ValueError:
        return False


def needs_rehash(hashed: str) -> bool:
    return _pwd_context.needs_update(hashed)


# --------------------------------------------------------------------- JWT
def _encode(payload: dict[str, Any], expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    to_encode = payload.copy()
    to_encode.update(
        {
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
            "jti": str(uuid.uuid4()),
        }
    )
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(
    *, user_id: uuid.UUID, role: str, permissions: list[str]
) -> str:
    return _encode(
        {
            "sub": str(user_id),
            "type": TokenType.ACCESS.value,
            "role": role,
            "perms": permissions,
        },
        timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
    )


def create_mfa_challenge_token(*, user_id: uuid.UUID) -> str:
    return _encode(
        {"sub": str(user_id), "type": TokenType.MFA_CHALLENGE.value},
        timedelta(minutes=settings.MFA_CHALLENGE_MINUTES),
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any] | None:
    """Return the payload, or None if the token is invalid/expired/wrong type."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    if payload.get("type") != expected_type.value:
        return None
    return payload


# ---------------------------------------------------------- opaque tokens
def generate_opaque_token(nbytes: int = 32) -> str:
    """Refresh / reset / verification tokens handed to the client."""
    return secrets.token_urlsafe(nbytes)


def hash_opaque_token(token: str) -> str:
    """Only the hash is ever stored, so a DB leak does not yield live tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def compare_digest(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


# ------------------------------------------------------------------- TOTP
def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(*, secret: str, account_name: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_name, issuer_name=settings.TOTP_ISSUER
    )


def verify_totp(*, secret: str, code: str, valid_window: int = 1) -> bool:
    """valid_window=1 tolerates one 30s step of clock drift."""
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=valid_window)


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [secrets.token_hex(5).upper() for _ in range(count)]
