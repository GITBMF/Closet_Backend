"""Create the first administrator on first launch.

Runs on every startup but does nothing unless ALL of these hold:

  * BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD are both set
  * the password satisfies the normal policy
  * no administrator exists yet

There is deliberately no default e-mail or password. Shipping software with
built-in credentials is how "admin/admin" ends up on the public internet;
if the operator has not chosen a value, no account is created.

The account is flagged `must_change_password`, so the bootstrap password is
single-use: the holder can read their own profile and set a new password, and
nothing else, until they do.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.core import security
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.identity.constants import ActorType, AuditAction, UserRole
from app.modules.identity.models import AuditLog, User

logger = logging.getLogger("closet.bootstrap")


def _password_is_acceptable(password: str) -> tuple[bool, str]:
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"shorter than {settings.PASSWORD_MIN_LENGTH} characters"
    if len(password.encode("utf-8")) > 72:
        return False, "longer than 72 bytes"
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return False, "must contain both letters and digits"
    if password.lower() in {"password", "changeme", "admin123", "closet123"}:
        return False, "is a well-known default"
    return True, ""


async def ensure_bootstrap_admin() -> None:
    """Idempotent: safe to call on every startup."""
    email = settings.BOOTSTRAP_ADMIN_EMAIL.strip().lower()
    password = settings.BOOTSTRAP_ADMIN_PASSWORD

    if not email or not password:
        logger.debug("bootstrap admin not configured — skipping")
        return

    ok, why = _password_is_acceptable(password)
    if not ok:
        # Loud, but the API still starts: a weak bootstrap password should not
        # take the storefront down.
        logger.error(
            "BOOTSTRAP_ADMIN_PASSWORD rejected (%s). No administrator was "
            "created. Fix the value and restart, or run "
            "scripts/manage_admin.py create.",
            why,
        )
        return

    async with AsyncSessionLocal() as db:
        admins = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(User)
                    .where(User.role == UserRole.ADMIN, User.deleted_at.is_(None))
                )
            ).scalar_one()
        )
        if admins:
            logger.debug("%d administrator(s) already exist — skipping bootstrap", admins)
            return

        existing = (
            await db.execute(
                select(User).where(
                    func.lower(User.email) == email, User.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            # The address is already a customer: promote rather than duplicate.
            previous = existing.role
            existing.role = UserRole.ADMIN
            existing.must_change_password = True
            db.add(
                AuditLog(
                    actor_type=ActorType.SYSTEM,
                    actor_id=existing.id,
                    action=AuditAction.USER_ROLE_CHANGED,
                    entity_type="user",
                    entity_id=str(existing.id),
                    payload={
                        "via": "bootstrap",
                        "from": previous.value,
                        "to": UserRole.ADMIN.value,
                    },
                )
            )
            await db.commit()
            logger.warning(
                "bootstrap: promoted existing account %s to administrator; "
                "a password change is required at next login",
                email,
            )
            return

        user = User(
            email=email,
            full_name=settings.BOOTSTRAP_ADMIN_NAME.strip() or "Administrateur",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash=security.hash_password(password),
            must_change_password=True,
        )
        db.add(user)
        await db.flush()
        db.add(
            AuditLog(
                actor_type=ActorType.SYSTEM,
                actor_id=user.id,
                action=AuditAction.USER_REGISTERED,
                entity_type="user",
                entity_id=str(user.id),
                payload={"via": "bootstrap", "role": UserRole.ADMIN.value},
            )
        )
        await db.commit()

    logger.warning(
        "bootstrap: administrator %s created. The password from "
        "BOOTSTRAP_ADMIN_PASSWORD must be changed at first login, and "
        "two-factor authentication is not yet enrolled.",
        email,
    )