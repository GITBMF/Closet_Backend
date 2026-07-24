"""Authentication for the internal /ops panel.

Reuses the identity module: same users table, same bcrypt hashes, same
lockout counters. The panel is administrator-only — a customer or sourcer
with valid credentials is refused, even though the password is correct.

This is a SEPARATE session from the API's JWT: the panel is a browser tool
and uses a signed session cookie, while the mobile app and the Next.js back
office use bearer tokens.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError, LoginFailed

from app.core import security
from app.core.database import AsyncSessionLocal
from app.modules.identity.constants import ActorType, AuditAction, UserRole
from app.modules.identity.models import AuditLog, User

SESSION_KEY = "ops_user_id"


class OpsAuthProvider(AuthProvider):
    """Username = the administrator's e-mail address."""

    async def login(
        self,
        username: str,
        password: str,
        remember_me: bool,
        request: Request,
        response: Response,
    ) -> Response:
        if len(username) < 3:
            raise FormValidationError({"username": "Adresse e-mail requise."})

        async with AsyncSessionLocal() as db:
            user = (
                await db.execute(
                    select(User).where(
                        User.email == username.lower().strip(),
                        User.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

            # Uniform failure — never reveal which part was wrong.
            if user is None or not security.verify_password(password, user.password_hash):
                raise LoginFailed("Identifiants incorrects.")

            if user.locked_until and user.locked_until > datetime.now(UTC):
                raise LoginFailed("Compte temporairement bloqué.")

            if not user.is_active:
                raise LoginFailed("Ce compte est désactivé.")

            if user.role is not UserRole.ADMIN:
                # Correct password, wrong role: log it, it is worth knowing.
                db.add(
                    AuditLog(
                        actor_type=ActorType.SYSTEM,
                        actor_id=user.id,
                        action="ops.login_denied",
                        entity_type="user",
                        entity_id=str(user.id),
                        payload={"role": user.role.value},
                    )
                )
                await db.commit()
                raise LoginFailed("Accès réservé aux administrateurs.")

            db.add(
                AuditLog(
                    actor_type=ActorType.ADMIN,
                    actor_id=user.id,
                    action=AuditAction.USER_LOGGED_IN,
                    entity_type="user",
                    entity_id=str(user.id),
                    payload={"surface": "ops"},
                )
            )
            await db.commit()

            request.session.update({SESSION_KEY: str(user.id)})

        return response

    async def is_authenticated(self, request: Request) -> bool:
        raw_id = request.session.get(SESSION_KEY)
        if not raw_id:
            return False

        try:
            user_id = uuid.UUID(raw_id)
        except ValueError:
            return False

        async with AsyncSessionLocal() as db:
            user = (
                await db.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()

        # Re-checked on EVERY request: a demoted or disabled administrator
        # loses the panel immediately, not when the cookie expires.
        if user is None or not user.is_active or user.deleted_at is not None:
            return False
        if user.role is not UserRole.ADMIN:
            return False

        request.state.user = user
        return True

    def get_admin_user(self, request: Request) -> AdminUser | None:
        user = getattr(request.state, "user", None)
        if user is None:
            return None
        return AdminUser(username=user.full_name or user.email)

    async def logout(self, request: Request, response: Response) -> Response:
        request.session.clear()
        return response