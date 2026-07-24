"""FastAPI dependencies: authentication and authorisation guards.

Usage in any module:

    @router.post("/pieces", dependencies=[Depends(require_permission(Permission.CATALOGUE_WRITE))])
    async def create_piece(...): ...

    async def my_orders(user: CurrentUser): ...
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.modules.identity.constants import Permission, TokenType, UserRole, role_has
from app.modules.identity.models import User
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.service import IdentityService, RequestContext

_bearer = HTTPBearer(auto_error=False)


def get_request_context(request: Request) -> RequestContext:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else None
    )
    return RequestContext(ip=ip, user_agent=request.headers.get("user-agent"))


def get_identity_service(db: Annotated[AsyncSession, Depends(get_db)]) -> IdentityService:
    return IdentityService(db)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Jeton d'accès manquant.", code="missing_token")

    payload = security.decode_token(
        credentials.credentials, expected_type=TokenType.ACCESS
    )
    if payload is None:
        raise AuthenticationError("Jeton invalide ou expiré.", code="invalid_token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Jeton malformé.", code="invalid_token") from exc

    user = await IdentityRepository(db).get_user(user_id)
    if user is None:
        raise AuthenticationError("Compte introuvable.", code="account_unavailable")
    if not user.is_active:
        raise PermissionDeniedError("Ce compte est désactivé.", code="account_disabled")

    # The role may have changed since the token was minted; the DB wins.
    if payload.get("role") != user.role.value:
        raise AuthenticationError(
            "Vos droits ont changé, reconnectez-vous.", code="stale_token"
        )
    return user


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """For guest-friendly endpoints (checkout, catalogue)."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials=credentials, db=db)
    except (AuthenticationError, PermissionDeniedError):
        return None


async def get_ready_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """A user who may actually use the API.

    An account flagged `must_change_password` (bootstrap or recovery) is held
    here: it can read its own profile and set a new password, nothing else.
    """
    if user.must_change_password:
        raise PermissionDeniedError(
            "Vous devez définir un nouveau mot de passe avant de continuer.",
            code="password_change_required",
        )
    return user


#: Default for every protected route.
CurrentUser = Annotated[User, Depends(get_ready_user)]

#: For the few endpoints that must stay reachable while the password is
#: pending: GET/PATCH /me, POST /me/password, POST /auth/logout.
PendingUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
Ctx = Annotated[RequestContext, Depends(get_request_context)]
Service = Annotated[IdentityService, Depends(get_identity_service)]


def require_permission(
    *permissions: Permission,
) -> Callable[[User], Awaitable[User]]:
    """Guard requiring ALL listed permissions."""

    async def _guard(user: CurrentUser) -> User:
        missing = [p for p in permissions if not role_has(user.role, p)]
        if missing:
            raise PermissionDeniedError(
                "Vous n'avez pas les droits nécessaires.",
                code="permission_denied",
                details={"missing": [p.value for p in missing]},
            )
        return user

    return _guard


def require_any_permission(
    *permissions: Permission,
) -> Callable[[User], Awaitable[User]]:
    async def _guard(user: CurrentUser) -> User:
        if not any(role_has(user.role, p) for p in permissions):
            raise PermissionDeniedError(
                "Vous n'avez pas les droits nécessaires.",
                code="permission_denied",
                details={"any_of": [p.value for p in permissions]},
            )
        return user

    return _guard


def require_role(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    async def _guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDeniedError(
                "Accès réservé.",
                code="role_required",
                details={"allowed": [r.value for r in roles]},
            )
        return user

    return _guard


#: Shorthand for the back office.
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]