"""Internal operations panel (Starlette-Admin), mounted at /ops.

This is an ENGINEERING tool, not the client deliverable. The customer-facing
administrator back office is the Next.js application specified in the
requirements. Use this to seed data, inspect rows and unstick records while
the real back office is being built.

Disabled unless OPS_ENABLED=true, and it refuses to start in production
unless OPS_ALLOW_IN_PROD is also set — see mount_ops().
"""

from __future__ import annotations

from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette_admin.contrib.sqla import Admin, ModelView

from app.core.config import settings
from app.core.database import engine
from app.modules.identity.models import (
    AuditLog,
    DeviceToken,
    PasswordResetToken,
    RefreshToken,
    User,
)
from app.ops.auth import OpsAuthProvider


class UserView(ModelView):
    identity = "user"
    name = "Utilisateur"
    label = "Utilisateurs"
    icon = "fa fa-users"

    fields = [
        "id", "email", "full_name", "phone", "city", "role",
        "is_active", "totp_enabled_at", "failed_login_count",
        "locked_until", "last_login_at", "created_at", "deleted_at",
    ]
    exclude_fields_from_list = ["id", "city", "totp_enabled_at", "deleted_at"]
    exclude_fields_from_create = [
        "failed_login_count", "locked_until", "last_login_at", "deleted_at"
    ]
    searchable_fields = ["email", "full_name", "phone"]
    sortable_fields = ["email", "full_name", "role", "created_at", "last_login_at"]
    fields_default_sort = [("created_at", True)]

    # password_hash and totp_secret are absent from `fields` on purpose:
    # the panel must never display or edit a credential.


class RefreshTokenView(ModelView):
    identity = "refresh-token"
    name = "Session"
    label = "Sessions"
    icon = "fa fa-key"

    fields = [
        "id", "user_id", "user_agent", "ip_address",
        "expires_at", "rotated_at", "revoked_at", "created_at",
    ]
    exclude_fields_from_list = ["id"]
    sortable_fields = ["created_at", "expires_at"]
    fields_default_sort = [("created_at", True)]

    # read-only: revoking must go through the API so the audit trail records it
    def can_create(self, request) -> bool:  # noqa: ANN001
        return False

    def can_edit(self, request) -> bool:  # noqa: ANN001
        return False


class DeviceTokenView(ModelView):
    identity = "device-token"
    name = "Appareil"
    label = "Appareils (push)"
    icon = "fa fa-mobile-screen"

    fields = ["id", "user_id", "platform", "marketing_opt_in", "created_at", "last_seen_at"]
    sortable_fields = ["created_at", "last_seen_at"]


class PasswordResetTokenView(ModelView):
    identity = "password-reset"
    name = "Réinitialisation"
    label = "Réinitialisations"
    icon = "fa fa-unlock"

    fields = ["id", "user_id", "expires_at", "used_at", "created_at"]
    fields_default_sort = [("created_at", True)]

    def can_create(self, request) -> bool:  # noqa: ANN001
        return False

    def can_edit(self, request) -> bool:  # noqa: ANN001
        return False


class AuditLogView(ModelView):
    identity = "audit-log"
    name = "Journal"
    label = "Journal d'audit"
    icon = "fa fa-clipboard-list"

    fields = [
        "id", "created_at", "action", "actor_type", "actor_id",
        "entity_type", "entity_id", "ip_address", "payload",
    ]
    searchable_fields = ["action", "entity_type", "entity_id"]
    sortable_fields = ["created_at", "action"]
    fields_default_sort = [("created_at", True)]

    # append-only: the audit trail is evidence, never editable
    def can_create(self, request) -> bool:  # noqa: ANN001
        return False

    def can_edit(self, request) -> bool:  # noqa: ANN001
        return False

    def can_delete(self, request) -> bool:  # noqa: ANN001
        return False


def build_admin() -> Admin:
    admin = Admin(
        engine,
        title="ClosET · Ops",
        base_url=settings.OPS_BASE_URL,
        route_name="ops",
        logo_url=settings.OPS_LOGO_URL or None,
        login_logo_url=settings.OPS_LOGO_URL or None,
        auth_provider=OpsAuthProvider(),
        middlewares=[
            Middleware(
                SessionMiddleware,
                secret_key=settings.OPS_SESSION_SECRET or settings.JWT_SECRET,
                session_cookie="closet_ops",
                https_only=settings.ENVIRONMENT == "prod",
                max_age=60 * 60 * 8,          # one working day
                same_site="lax",
            )
        ],
        debug=settings.DEBUG,
    )

    admin.add_view(UserView(User))
    admin.add_view(RefreshTokenView(RefreshToken))
    admin.add_view(DeviceTokenView(DeviceToken))
    admin.add_view(PasswordResetTokenView(PasswordResetToken))
    admin.add_view(AuditLogView(AuditLog))
    return admin


def mount_ops(app) -> bool:  # noqa: ANN001
    """Attach the panel if it is enabled. Returns True when mounted."""
    if not settings.OPS_ENABLED:
        return False

    if settings.ENVIRONMENT == "prod" and not settings.OPS_ALLOW_IN_PROD:
        # Deliberate: an internal CRUD panel on a public production host is a
        # standing invitation. Set OPS_ALLOW_IN_PROD=true only behind a VPN,
        # an IP allow-list or an SSH tunnel.
        raise RuntimeError(
            "OPS_ENABLED=true in production without OPS_ALLOW_IN_PROD=true. "
            "Restrict access first (VPN / IP allow-list / SSH tunnel)."
        )

    build_admin().mount_to(app)
    return True