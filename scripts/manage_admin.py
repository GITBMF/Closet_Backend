#!/usr/bin/env python3
"""Administrator management — bootstrap and break-glass recovery.

Run it on the server, never over the network:

    # inside docker
    docker compose exec api python scripts/manage_admin.py create
    # on the host (venv active)
    python scripts/manage_admin.py create

Commands
--------
  create        create the first (or an additional) administrator
  promote       give an existing account the admin role
  set-password  reset a password when someone is locked out
  reset-mfa     clear TOTP so the holder can enrol a new authenticator
  list          show every administrator

Why a CLI and not an endpoint: bootstrapping must not be reachable from the
internet, and `UPDATE users SET role='admin'` in psql leaves no audit trail
and silently accepts a mistyped address.

Every command writes to audit_logs with actor_type='system' and
payload {"via": "cli"}, so nothing here is invisible.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import UTC, datetime
from pathlib import Path

# allow `python scripts/manage_admin.py` from the repository root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core import security  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.modules.identity.constants import (  # noqa: E402
    ActorType,
    AuditAction,
    UserRole,
)
from app.modules.identity.models import AuditLog, User  # noqa: E402

# Reuse the API's password rules so the CLI cannot create an account the
# API would have rejected.
from app.modules.identity.schemas import _validate_password as check_password  # noqa: E402


# --------------------------------------------------------------- helpers
def out(msg: str = "") -> None:
    print(msg, flush=True)


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def read_password(supplied: str | None, *, from_stdin: bool) -> str:
    """Take the password from --password, stdin, or an interactive prompt."""
    if from_stdin:
        pw = sys.stdin.readline().rstrip("\n")
        if not pw:
            fail("no password received on stdin")
        return pw
    if supplied:
        return supplied
    if not sys.stdin.isatty():
        fail("no terminal available — use --password-stdin")
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Confirm password: "):
        fail("passwords do not match")
    return pw


def validate(password: str) -> str:
    try:
        return check_password(password)
    except ValueError as exc:
        fail(str(exc))
        raise  # unreachable, keeps type checkers happy


async def audit(db, *, action: str, user: User, extra: dict | None = None) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.SYSTEM,
            actor_id=user.id,
            action=action,
            entity_type="user",
            entity_id=str(user.id),
            payload={"via": "cli", **(extra or {})},
        )
    )


async def get_by_email(db, email: str) -> User | None:
    return (
        await db.execute(
            select(User).where(
                func.lower(User.email) == email.lower().strip(),
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def enrol_mfa(db, user: User, *, interactive: bool) -> None:
    """Enrol TOTP now, verifying a code before enabling it.

    Enabling without verification is how an administrator locks themselves
    out permanently: ADMIN_REQUIRES_2FA prevents them turning it off.
    """
    if not interactive or not sys.stdin.isatty():
        out("  ! 2FA not enrolled. Do it at once via POST /api/v1/me/mfa/setup,")
        out("    or re-run:  manage_admin.py reset-mfa --email <address>")
        return

    secret = security.generate_totp_secret()
    uri = security.totp_provisioning_uri(secret=secret, account_name=user.email or str(user.id))

    out()
    out("  Two-factor setup — scan this in Google Authenticator / Authy / 1Password:")
    out(f"    {uri}")
    out(f"  Or enter the key manually: {secret}")
    out()

    for attempt in (1, 2, 3):
        code = input(f"  6-digit code (attempt {attempt}/3, blank to skip): ").strip()
        if not code:
            out("  ! skipped — 2FA is NOT active on this account.")
            return
        if security.verify_totp(secret=secret, code=code):
            user.totp_secret = secret
            user.totp_enabled_at = datetime.now(UTC)
            await audit(db, action=AuditAction.MFA_ENABLED, user=user)
            out("  ✓ two-factor authentication enabled")
            return
        out("  wrong code — check the clock on your phone")
    out("  ! three failed attempts; 2FA is NOT active.")


async def count_admins(db) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.role == UserRole.ADMIN, User.deleted_at.is_(None))
            )
        ).scalar_one()
    )


# -------------------------------------------------------------- commands
async def cmd_create(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        existing = await count_admins(db)
        if existing and not args.force:
            fail(
                f"{existing} administrator(s) already exist. Create further "
                "administrators from the back office (POST /api/v1/admin/users), "
                "or pass --force if you really mean it."
            )

        email = args.email or input("E-mail: ").strip()
        if await get_by_email(db, email):
            fail(f"{email} already exists — use `promote` instead.")

        name = args.name or input("Full name: ").strip()
        if len(name) < 2:
            fail("full name is too short")

        password = validate(read_password(args.password, from_stdin=args.password_stdin))

        user = User(
            email=email.lower().strip(),
            full_name=name,
            phone=args.phone,
            role=UserRole.ADMIN,
            is_active=True,
            password_hash=security.hash_password(password),
        )
        db.add(user)
        await db.flush()

        await audit(
            db,
            action=AuditAction.USER_REGISTERED,
            user=user,
            extra={"role": UserRole.ADMIN.value, "bootstrap": not existing},
        )

        out(f"  ✓ administrator created: {user.email}  ({user.id})")
        await enrol_mfa(db, user, interactive=not args.no_mfa)
        await db.commit()

        if settings.ADMIN_REQUIRES_2FA and not user.mfa_enabled:
            out()
            out("  WARNING: ADMIN_REQUIRES_2FA is on but this account has no 2FA yet.")
            out("           Enrol it before exposing the API.")


async def cmd_promote(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        user = await get_by_email(db, args.email)
        if user is None:
            fail(f"no account for {args.email}")
        if user.role is UserRole.ADMIN:
            out(f"  {user.email} is already an administrator.")
            return

        previous = user.role
        user.role = UserRole.ADMIN
        # permissions live inside issued access tokens; kill existing sessions
        from app.modules.identity.repository import IdentityRepository

        revoked = await IdentityRepository(db).revoke_all_for_user(user.id)
        await audit(
            db,
            action=AuditAction.USER_ROLE_CHANGED,
            user=user,
            extra={"from": previous.value, "to": UserRole.ADMIN.value},
        )
        out(f"  ✓ {user.email} promoted from {previous.value} to admin "
            f"({revoked} session(s) revoked — they must log in again)")
        await enrol_mfa(db, user, interactive=not args.no_mfa)
        await db.commit()


async def cmd_set_password(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        user = await get_by_email(db, args.email)
        if user is None:
            fail(f"no account for {args.email}")

        password = validate(read_password(args.password, from_stdin=args.password_stdin))
        user.password_hash = security.hash_password(password)
        user.failed_login_count = 0
        user.locked_until = None

        from app.modules.identity.repository import IdentityRepository

        revoked = await IdentityRepository(db).revoke_all_for_user(user.id)
        await audit(db, action=AuditAction.USER_PASSWORD_CHANGED, user=user)
        await db.commit()
        out(f"  ✓ password reset for {user.email}; account unlocked; "
            f"{revoked} session(s) revoked")


async def cmd_reset_mfa(args: argparse.Namespace) -> None:
    """Break-glass: the holder lost their authenticator."""
    async with AsyncSessionLocal() as db:
        user = await get_by_email(db, args.email)
        if user is None:
            fail(f"no account for {args.email}")

        user.totp_secret = None
        user.totp_enabled_at = None
        await audit(db, action=AuditAction.MFA_DISABLED, user=user, extra={"reason": "recovery"})
        out(f"  ✓ 2FA cleared for {user.email}")
        await enrol_mfa(db, user, interactive=not args.no_mfa)
        await db.commit()


async def cmd_list(_: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(User)
                .where(User.role == UserRole.ADMIN, User.deleted_at.is_(None))
                .order_by(User.created_at)
            )
        ).scalars().all()

        if not rows:
            out("  no administrators — run:  manage_admin.py create")
            return
        out(f"  {len(rows)} administrator(s):")
        for u in rows:
            flags = []
            flags.append("2FA" if u.mfa_enabled else "NO 2FA")
            if not u.is_active:
                flags.append("DISABLED")
            if u.locked_until and u.locked_until > datetime.now(UTC):
                flags.append("LOCKED")
            last = u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "never"
            out(f"    {u.email:34} {', '.join(flags):18} last login: {last}")


# ------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage_admin.py",
        description="Create and recover ClosET administrator accounts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def creds(p: argparse.ArgumentParser) -> None:
        p.add_argument("--password", help="avoid on a shared shell: it lands in history")
        p.add_argument("--password-stdin", action="store_true",
                       help="read the password from stdin (safe for scripts)")
        p.add_argument("--no-mfa", action="store_true", help="skip TOTP enrolment")

    p = sub.add_parser("create", help="create an administrator")
    p.add_argument("--email")
    p.add_argument("--name")
    p.add_argument("--phone")
    p.add_argument("--force", action="store_true",
                   help="create even though administrators already exist")
    creds(p)
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("promote", help="promote an existing account")
    p.add_argument("--email", required=True)
    creds(p)
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("set-password", help="reset a password (break-glass)")
    p.add_argument("--email", required=True)
    creds(p)
    p.set_defaults(func=cmd_set_password)

    p = sub.add_parser("reset-mfa", help="clear TOTP so a new device can enrol")
    p.add_argument("--email", required=True)
    creds(p)
    p.set_defaults(func=cmd_reset_mfa)

    p = sub.add_parser("list", help="list administrators")
    p.set_defaults(func=cmd_list)

    return parser


async def main() -> None:
    args = build_parser().parse_args()
    try:
        await args.func(args)
    except OSError as exc:  # database unreachable
        fail(
            f"cannot reach the database at {settings.POSTGRES_HOST}:"
            f"{settings.POSTGRES_PORT} ({exc}).\n"
            "       Is it running?  docker compose ps\n"
            "       Inside docker use:  docker compose exec api "
            "python scripts/manage_admin.py ..."
        )
    except KeyboardInterrupt:
        out("\n  cancelled")
        raise SystemExit(130) from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())