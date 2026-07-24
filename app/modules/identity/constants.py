"""Roles, permissions and the RBAC matrix.

This is the single source of truth for "who may do what" across the whole
platform. Other modules import Permission and guard their routes with
`require_permission(...)` — they never re-implement role checks.

Design notes
------------
* Roles come from the requirements spec: Customer, Sourcer, Administrator,
  Courier. A person can be both customer and sourcer with ONE account:
  the SOURCER role is granted when the administrator approves their sourcer
  membership, and it is additive (a sourcer keeps customer permissions).
* Per spec 7.3 a courier normally has NO account and acts through a signed,
  limited-use link. The COURIER role exists for the case where the client
  later wants named courier accounts; the delivery module can rely on the
  same permission either way.
* Permissions are strings of the form "<resource>:<action>[:<scope>]" so they
  read well in logs and can be stored as-is in the audit trail.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    SOURCER = "sourcer"
    COURIER = "courier"
    ADMIN = "admin"


class ActorType(StrEnum):
    """Who performed an action — used by every *_status_history table."""

    CUSTOMER = "customer"
    SOURCER = "sourcer"
    ADMIN = "admin"
    COURIER = "courier"
    SYSTEM = "system"


class Permission(StrEnum):
    # --- account (everyone authenticated) ---------------------------
    ACCOUNT_READ_OWN = "account:read:own"
    ACCOUNT_UPDATE_OWN = "account:update:own"

    # --- catalogue ---------------------------------------------------
    CATALOGUE_READ = "catalogue:read"
    CATALOGUE_WRITE = "catalogue:write"
    CATALOGUE_PUBLISH = "catalogue:publish"

    # --- orders ------------------------------------------------------
    ORDER_CREATE = "order:create"
    ORDER_READ_OWN = "order:read:own"
    ORDER_READ_ALL = "order:read:all"
    ORDER_UPDATE_STATUS = "order:update:status"

    # --- payments ----------------------------------------------------
    PAYMENT_RECONCILE = "payment:reconcile"
    PAYMENT_REFUND = "payment:refund"

    # --- sourcing ----------------------------------------------------
    SUBMISSION_CREATE = "submission:create"
    SUBMISSION_READ_OWN = "submission:read:own"
    SUBMISSION_REVIEW = "submission:review"
    SOURCER_APPROVE = "sourcer:approve"
    PAYOUT_READ_OWN = "payout:read:own"
    PAYOUT_MANAGE = "payout:manage"

    # --- delivery ----------------------------------------------------
    DELIVERY_MANAGE = "delivery:manage"
    DELIVERY_UPDATE_STATUS = "delivery:update:status"
    DELIVERY_RATE_MANAGE = "delivery:rate:manage"

    # --- merchandising ----------------------------------------------
    PRIVILEGE_MANAGE = "privilege:manage"
    SPONSOR_MANAGE = "sponsor:manage"
    SHOWCASE_MANAGE = "showcase:manage"

    # --- returns -----------------------------------------------------
    RETURN_MANAGE = "return:manage"

    # --- back office -------------------------------------------------
    DASHBOARD_READ = "dashboard:read"
    USER_READ_ALL = "user:read:all"
    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"


#: Permissions every authenticated user has, whatever their role.
_BASE: frozenset[Permission] = frozenset(
    {
        Permission.ACCOUNT_READ_OWN,
        Permission.ACCOUNT_UPDATE_OWN,
        Permission.CATALOGUE_READ,
    }
)

_CUSTOMER: frozenset[Permission] = _BASE | {
    Permission.ORDER_CREATE,
    Permission.ORDER_READ_OWN,
}

#: A sourcer is a customer too — they can still buy.
_SOURCER: frozenset[Permission] = _CUSTOMER | {
    Permission.SUBMISSION_CREATE,
    Permission.SUBMISSION_READ_OWN,
    Permission.PAYOUT_READ_OWN,
}

_COURIER: frozenset[Permission] = _BASE | {
    Permission.DELIVERY_UPDATE_STATUS,
}

#: The single administrator can do everything.
_ADMIN: frozenset[Permission] = frozenset(Permission)

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.CUSTOMER: _CUSTOMER,
    UserRole.SOURCER: _SOURCER,
    UserRole.COURIER: _COURIER,
    UserRole.ADMIN: _ADMIN,
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, _BASE)


def role_has(role: UserRole, permission: Permission) -> bool:
    return permission in permissions_for(role)


# --- audit actions -----------------------------------------------------
class AuditAction(StrEnum):
    USER_REGISTERED = "user.registered"
    USER_LOGGED_IN = "user.logged_in"
    USER_LOGIN_FAILED = "user.login_failed"
    USER_LOCKED = "user.locked"
    USER_LOGGED_OUT = "user.logged_out"
    USER_TOKEN_REFRESHED = "user.token_refreshed"
    USER_TOKEN_REUSE_DETECTED = "user.token_reuse_detected"
    USER_PASSWORD_CHANGED = "user.password_changed"
    USER_PASSWORD_RESET_REQUESTED = "user.password_reset_requested"
    USER_PASSWORD_RESET_COMPLETED = "user.password_reset_completed"
    USER_PROFILE_UPDATED = "user.profile_updated"
    USER_ROLE_CHANGED = "user.role_changed"
    USER_DEACTIVATED = "user.deactivated"
    USER_REACTIVATED = "user.reactivated"
    USER_DELETED = "user.deleted"
    MFA_ENABLED = "mfa.enabled"
    MFA_DISABLED = "mfa.disabled"
    MFA_CHALLENGE_FAILED = "mfa.challenge_failed"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    MFA_CHALLENGE = "mfa_challenge"