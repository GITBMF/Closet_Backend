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
from starlette.responses import RedirectResponse, Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError, LoginFailed

from app.core import security
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.identity.constants import ActorType, AuditAction, UserRole
from app.modules.identity.models import AuditLog, User

SESSION_KEY = "ops_user_id"
MFA_OK_KEY = "ops_mfa_ok"    # set only after a valid TOTP code THIS session


# Route names that a partially-authenticated admin must reach WITHOUT passing
# the full is_authenticated gate: the first-login onboarding pages and the
# TOTP challenge. Starlette-Admin's AuthMiddleware guards every other route.
ONBOARDING_ROUTE_NAMES = [
    "ops-onboarding",
    "ops-onboarding-email",
    "ops-onboarding-password",
    "ops-onboarding-mfa",
    "ops-verify-2fa",
]


class OpsAuthProvider(AuthProvider):
    """Username = the administrator's e-mail address."""

    def __init__(self, *args, **kwargs) -> None:
        # allow the onboarding + 2FA-challenge routes through the auth
        # middleware; they do their own session checks internally.
        existing = list(kwargs.pop("allow_routes", []) or [])
        kwargs["allow_routes"] = existing + ONBOARDING_ROUTE_NAMES
        super().__init__(*args, **kwargs)

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

            # Password is correct. Start a session but DO NOT trust it for the
            # panel yet — mark 2FA as not-yet-passed for this login.
            request.session.update({SESSION_KEY: str(user.id), MFA_OK_KEY: False})

            # Decide where to send them:
            #   1) must change a handed-out password  -> onboarding (step 1)
            #   2) 2FA required but not yet enrolled   -> onboarding (step 2)
            #   3) 2FA enrolled                        -> TOTP challenge
            #   4) otherwise (2FA off)                 -> straight in
            needs_password = user.must_change_password
            needs_enrol = settings.ADMIN_REQUIRES_2FA and not user.mfa_enabled

            if needs_password or needs_enrol:
                return RedirectResponse("/ops/onboarding", status_code=302)
            if user.mfa_enabled:
                return RedirectResponse("/ops/verify-2fa", status_code=302)
            # no 2FA in play at all: this login is fully authenticated
            request.session[MFA_OK_KEY] = True

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
        if user.must_change_password:
            # Re-checked per request, like the role: a flag set while a session
            # is open (e.g. an admin reset by the CLI) takes effect at once.
            return False

        if user.email_verified_at is None:
            # E-mail must be verified before the panel opens; the onboarding
            # flow sends a code and stamps email_verified_at.
            return False

        # 2FA is a hard prerequisite. An admin without it enrolled is held out
        # (they can still reach /ops/onboarding to enrol).
        if settings.ADMIN_REQUIRES_2FA and not user.mfa_enabled:
            return False

        # Enrolled is not enough: they must have PASSED the TOTP challenge in
        # THIS session. Distinguishes "2FA set up" (a DB fact) from "2FA proven
        # this login" (a session fact) — a stolen cookie alone can't skip it.
        if user.mfa_enabled and not request.session.get(MFA_OK_KEY):
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