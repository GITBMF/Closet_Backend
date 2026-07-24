"""Integration tests for the identity module (real PostgreSQL)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pyotp
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.db.registry import Base
from app.main import create_app
from app.modules.identity.constants import UserRole

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        # The PG enums are declared with create_type=False because the Alembic
        # migration owns them; mirror that here so the two stay in step.
        await conn.execute(
            text("CREATE TYPE user_role AS ENUM ('customer','sourcer','courier','admin')")
        )
        await conn.execute(
            text(
                "CREATE TYPE actor_type AS ENUM "
                "('customer','sourcer','admin','courier','system')"
            )
        )
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _clean() -> AsyncGenerator[None, None]:
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE audit_logs, refresh_tokens, device_tokens, "
                "password_reset_tokens, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


API = "/api/v1"
GOOD = {"email": "awa@example.cm", "password": "Dressing2026", "full_name": "Awa K"}


async def register(client: AsyncClient, **over) -> dict:
    payload = {**GOOD, **over}
    r = await client.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def login(client: AsyncClient, **over) -> dict:
    payload = {"email": GOOD["email"], "password": GOOD["password"], **over}
    r = await client.post(f"{API}/auth/login", json=payload)
    return r.json() | {"_status": r.status_code}


async def make_admin(email: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("UPDATE users SET role='admin' WHERE email=:e"), {"e": email}
        )
        await s.commit()


# ================================================================= tests
class TestRegistration:
    async def test_register_returns_customer(self, client: AsyncClient):
        body = await register(client)
        assert body["role"] == UserRole.CUSTOMER
        assert body["mfa_enabled"] is False
        assert "password" not in body

    async def test_duplicate_email_rejected(self, client: AsyncClient):
        await register(client)
        r = await client.post(f"{API}/auth/register", json=GOOD)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "email_taken"

    async def test_weak_password_rejected(self, client: AsyncClient):
        r = await client.post(
            f"{API}/auth/register", json={**GOOD, "password": "short"}
        )
        assert r.status_code == 422

    async def test_password_without_digit_rejected(self, client: AsyncClient):
        r = await client.post(
            f"{API}/auth/register", json={**GOOD, "password": "onlyletters"}
        )
        assert r.status_code == 422

    async def test_invalid_phone_rejected(self, client: AsyncClient):
        r = await client.post(
            f"{API}/auth/register", json={**GOOD, "phone": "not-a-phone"}
        )
        assert r.status_code == 422


class TestLogin:
    async def test_login_returns_tokens(self, client: AsyncClient):
        await register(client)
        body = await login(client)
        assert body["_status"] == 200
        assert body["access_token"] and body["refresh_token"]
        assert body["user"]["email"] == GOOD["email"]

    async def test_wrong_password_rejected(self, client: AsyncClient):
        await register(client)
        body = await login(client, password="WrongPass123")
        assert body["_status"] == 401
        assert body["error"]["code"] == "invalid_credentials"

    async def test_unknown_email_same_error(self, client: AsyncClient):
        body = await login(client, email="ghost@example.cm")
        assert body["_status"] == 401
        # identical code => no account enumeration
        assert body["error"]["code"] == "invalid_credentials"

    async def test_lockout_after_max_failures(self, client: AsyncClient):
        await register(client)
        for _ in range(settings.MAX_FAILED_LOGINS):
            await login(client, password="Wrong12345")
        body = await login(client)  # correct password now
        assert body["_status"] == 429
        assert body["error"]["code"] == "account_locked"

    async def test_disabled_account_cannot_login(self, client: AsyncClient):
        await register(client)
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("UPDATE users SET is_active=false WHERE email=:e"),
                {"e": GOOD["email"]},
            )
            await s.commit()
        body = await login(client)
        assert body["_status"] == 403
        assert body["error"]["code"] == "account_disabled"


class TestTokens:
    async def test_refresh_rotates_token(self, client: AsyncClient):
        await register(client)
        first = await login(client)
        r = await client.post(
            f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert r.status_code == 200
        assert r.json()["refresh_token"] != first["refresh_token"]

    async def test_reuse_of_rotated_token_revokes_family(self, client: AsyncClient):
        await register(client)
        first = await login(client)
        second = (
            await client.post(
                f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}
            )
        ).json()

        # replay the OLD token -> theft signal
        replay = await client.post(
            f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "token_reuse_detected"

        # and the token issued from it is dead too
        after = await client.post(
            f"{API}/auth/refresh", json={"refresh_token": second["refresh_token"]}
        )
        assert after.status_code == 401

    async def test_logout_all_devices(self, client: AsyncClient):
        await register(client)
        a = await login(client)
        b = await login(client)
        r = await client.post(
            f"{API}/auth/logout",
            json={"all_devices": True},
            headers={"Authorization": f"Bearer {a['access_token']}"},
        )
        assert r.status_code == 200
        for session in (a, b):
            dead = await client.post(
                f"{API}/auth/refresh", json={"refresh_token": session["refresh_token"]}
            )
            assert dead.status_code == 401

    async def test_missing_token_rejected(self, client: AsyncClient):
        r = await client.get(f"{API}/me")
        assert r.status_code == 401

    async def test_garbage_token_rejected(self, client: AsyncClient):
        r = await client.get(
            f"{API}/me", headers={"Authorization": "Bearer not.a.jwt"}
        )
        assert r.status_code == 401


class TestAccount:
    async def test_me_exposes_permissions(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        r = await client.get(
            f"{API}/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert r.status_code == 200
        perms = r.json()["permissions"]
        assert "order:create" in perms
        assert "user:manage" not in perms  # customer must not have admin rights

    async def test_update_profile(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        r = await client.patch(
            f"{API}/me",
            json={"full_name": "Awa Kamdem", "city": "Yaoundé"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["full_name"] == "Awa Kamdem"

    async def test_change_password_revokes_sessions(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        r = await client.post(
            f"{API}/me/password",
            json={
                "current_password": GOOD["password"],
                "new_password": "NouveauPass2026",
            },
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 200
        dead = await client.post(
            f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert dead.status_code == 401
        assert (await login(client, password="NouveauPass2026"))["_status"] == 200

    async def test_change_password_wrong_current(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        r = await client.post(
            f"{API}/me/password",
            json={"current_password": "Nope12345", "new_password": "Autre12345"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 401


class TestPasswordReset:
    async def test_forgot_password_does_not_enumerate(self, client: AsyncClient):
        await register(client)
        known = await client.post(
            f"{API}/auth/forgot-password", json={"email": GOOD["email"]}
        )
        unknown = await client.post(
            f"{API}/auth/forgot-password", json={"email": "nobody@example.cm"}
        )
        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json()

    async def test_reset_with_invalid_token(self, client: AsyncClient):
        r = await client.post(
            f"{API}/auth/reset-password",
            json={"token": "invalid", "new_password": "Nouveau12345"},
        )
        assert r.status_code == 422


class TestMFA:
    async def _enable(self, client: AsyncClient, access: str) -> str:
        setup = await client.post(
            f"{API}/me/mfa/setup", headers={"Authorization": f"Bearer {access}"}
        )
        assert setup.status_code == 200
        secret = setup.json()["secret"]
        code = pyotp.TOTP(secret).now()
        confirm = await client.post(
            f"{API}/me/mfa/verify",
            json={"code": code},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert confirm.status_code == 200
        return secret

    async def test_login_requires_mfa_once_enabled(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        secret = await self._enable(client, tokens["access_token"])

        challenge = await login(client)
        assert challenge["_status"] == 200
        assert challenge.get("mfa_required") is True
        assert "access_token" not in challenge

        done = await client.post(
            f"{API}/auth/login/mfa",
            json={
                "challenge_token": challenge["challenge_token"],
                "code": pyotp.TOTP(secret).now(),
            },
        )
        assert done.status_code == 200
        assert done.json()["access_token"]

    async def test_bad_mfa_code_rejected(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        await self._enable(client, tokens["access_token"])
        challenge = await login(client)
        r = await client.post(
            f"{API}/auth/login/mfa",
            json={"challenge_token": challenge["challenge_token"], "code": "000000"},
        )
        assert r.status_code == 401

    async def test_admin_cannot_disable_mfa(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        secret = await self._enable(client, tokens["access_token"])
        await make_admin(GOOD["email"])

        fresh = await login(client)
        done = await client.post(
            f"{API}/auth/login/mfa",
            json={
                "challenge_token": fresh["challenge_token"],
                "code": pyotp.TOTP(secret).now(),
            },
        )
        access = done.json()["access_token"]
        r = await client.post(
            f"{API}/me/mfa/disable",
            json={"password": GOOD["password"], "code": pyotp.TOTP(secret).now()},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "mfa_required_for_admin"


class TestRBAC:
    async def _admin_tokens(self, client: AsyncClient) -> dict:
        await register(client, email="admin@closet.cm")
        await make_admin("admin@closet.cm")
        return await login(client, email="admin@closet.cm")

    async def test_customer_denied_admin_endpoints(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        r = await client.get(
            f"{API}/admin/users",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "permission_denied"

    async def test_admin_lists_users(self, client: AsyncClient):
        admin = await self._admin_tokens(client)
        await register(client)
        r = await client.get(
            f"{API}/admin/users",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["meta"]["total"] == 2

    async def test_admin_changes_role_and_kills_sessions(self, client: AsyncClient):
        admin = await self._admin_tokens(client)
        customer = await register(client)
        cust_tokens = await login(client)

        r = await client.put(
            f"{API}/admin/users/{customer['id']}/role",
            json={"role": "sourcer", "reason": "membership approved"},
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["role"] == "sourcer"

        # old refresh token revoked, old access token now stale
        dead = await client.post(
            f"{API}/auth/refresh", json={"refresh_token": cust_tokens["refresh_token"]}
        )
        assert dead.status_code == 401
        stale = await client.get(
            f"{API}/me",
            headers={"Authorization": f"Bearer {cust_tokens['access_token']}"},
        )
        assert stale.status_code == 401
        assert stale.json()["error"]["code"] == "stale_token"

    async def test_sourcer_permissions(self, client: AsyncClient):
        admin = await self._admin_tokens(client)
        customer = await register(client)
        await client.put(
            f"{API}/admin/users/{customer['id']}/role",
            json={"role": "sourcer"},
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        tokens = await login(client)
        me = await client.get(
            f"{API}/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        perms = me.json()["permissions"]
        assert "submission:create" in perms
        assert "order:create" in perms      # sourcer is still a customer
        assert "submission:review" not in perms

    async def test_admin_cannot_demote_self(self, client: AsyncClient):
        admin = await self._admin_tokens(client)
        me = await client.get(
            f"{API}/me", headers={"Authorization": f"Bearer {admin['access_token']}"}
        )
        r = await client.put(
            f"{API}/admin/users/{me.json()['id']}/role",
            json={"role": "customer"},
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "cannot_demote_self"

    async def test_admin_deactivates_user(self, client: AsyncClient):
        admin = await self._admin_tokens(client)
        customer = await register(client)
        r = await client.patch(
            f"{API}/admin/users/{customer['id']}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert r.status_code == 200
        assert (await login(client))["_status"] == 403

    async def test_admin_soft_deletes_user(self, client: AsyncClient):
        admin = await self._admin_tokens(client)
        customer = await register(client)
        r = await client.delete(
            f"{API}/admin/users/{customer['id']}",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert r.status_code == 204
        gone = await client.get(
            f"{API}/admin/users/{customer['id']}",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert gone.status_code == 404

    async def test_admin_creates_user_with_role(self, client: AsyncClient):
        admin = await self._admin_tokens(client)
        r = await client.post(
            f"{API}/admin/users",
            json={
                "email": "livreur@closet.cm",
                "full_name": "Paul Livreur",
                "role": "courier",
            },
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert r.status_code == 201
        assert r.json()["role"] == "courier"


class TestAudit:
    async def test_actions_are_recorded(self, client: AsyncClient):
        await register(client)
        await login(client, password="Wrong12345")
        await login(client)
        async with AsyncSessionLocal() as s:
            rows = (
                await s.execute(text("SELECT action FROM audit_logs ORDER BY id"))
            ).scalars().all()
        assert "user.registered" in rows
        assert "user.login_failed" in rows
        assert "user.logged_in" in rows

    async def test_admin_reads_user_audit(self, client: AsyncClient):
        await register(client, email="admin@closet.cm")
        await make_admin("admin@closet.cm")
        admin = await login(client, email="admin@closet.cm")
        me = await client.get(
            f"{API}/me", headers={"Authorization": f"Bearer {admin['access_token']}"}
        )
        r = await client.get(
            f"{API}/admin/users/{me.json()['id']}/audit",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["meta"]["total"] >= 1


class TestBootstrapAdmin:
    """First-launch administrator provisioning."""

    async def _bootstrap(self, email: str, password: str, name: str = "Boot Admin"):
        from app.core.config import settings as s
        from app.modules.identity.bootstrap import ensure_bootstrap_admin

        before = (s.BOOTSTRAP_ADMIN_EMAIL, s.BOOTSTRAP_ADMIN_PASSWORD, s.BOOTSTRAP_ADMIN_NAME)
        s.BOOTSTRAP_ADMIN_EMAIL, s.BOOTSTRAP_ADMIN_PASSWORD, s.BOOTSTRAP_ADMIN_NAME = (
            email, password, name,
        )
        try:
            await ensure_bootstrap_admin()
        finally:
            (s.BOOTSTRAP_ADMIN_EMAIL, s.BOOTSTRAP_ADMIN_PASSWORD,
             s.BOOTSTRAP_ADMIN_NAME) = before

    async def test_creates_admin_on_first_launch(self, client: AsyncClient):
        await self._bootstrap("boot@closet.cm", "Premier2026Secret")
        r = await client.post(
            f"{API}/auth/login",
            json={"email": "boot@closet.cm", "password": "Premier2026Secret"},
        )
        assert r.status_code == 200
        assert r.json()["user"]["role"] == UserRole.ADMIN
        assert r.json()["user"]["must_change_password"] is True

    async def test_is_idempotent(self, client: AsyncClient):
        await self._bootstrap("boot@closet.cm", "Premier2026Secret")
        await self._bootstrap("other@closet.cm", "Premier2026Secret")
        async with AsyncSessionLocal() as s:
            n = (
                await s.execute(text("SELECT count(*) FROM users WHERE role='admin'"))
            ).scalar_one()
        assert n == 1

    async def test_no_config_means_no_account(self, client: AsyncClient):
        await self._bootstrap("", "")
        async with AsyncSessionLocal() as s:
            n = (await s.execute(text("SELECT count(*) FROM users"))).scalar_one()
        assert n == 0

    async def test_weak_password_creates_nothing(self, client: AsyncClient):
        await self._bootstrap("boot@closet.cm", "admin123")
        async with AsyncSessionLocal() as s:
            n = (await s.execute(text("SELECT count(*) FROM users"))).scalar_one()
        assert n == 0

    async def test_promotes_an_existing_customer(self, client: AsyncClient):
        await register(client)                      # awa@example.cm, customer
        await self._bootstrap(GOOD["email"], "Premier2026Secret")
        async with AsyncSessionLocal() as s:
            role, flag = (
                await s.execute(
                    text("SELECT role, must_change_password FROM users WHERE email=:e"),
                    {"e": GOOD["email"]},
                )
            ).first()
        assert role == "admin" and flag is True


class TestForcedPasswordChange:
    async def _pending_admin(self, client: AsyncClient) -> dict:
        await TestBootstrapAdmin()._bootstrap("boot@closet.cm", "Premier2026Secret")
        return (
            await client.post(
                f"{API}/auth/login",
                json={"email": "boot@closet.cm", "password": "Premier2026Secret"},
            )
        ).json()

    async def test_protected_routes_are_blocked(self, client: AsyncClient):
        tokens = await self._pending_admin(client)
        r = await client.get(
            f"{API}/admin/users",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "password_change_required"

    async def test_me_stays_reachable(self, client: AsyncClient):
        tokens = await self._pending_admin(client)
        r = await client.get(
            f"{API}/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert r.status_code == 200
        assert r.json()["must_change_password"] is True

    async def test_changing_password_unlocks_everything(self, client: AsyncClient):
        tokens = await self._pending_admin(client)
        r = await client.post(
            f"{API}/me/password",
            json={
                "current_password": "Premier2026Secret",
                "new_password": "MonPropreMotDePasse2026",
            },
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 200

        fresh = await client.post(
            f"{API}/auth/login",
            json={"email": "boot@closet.cm", "password": "MonPropreMotDePasse2026"},
        )
        assert fresh.json()["user"]["must_change_password"] is False
        allowed = await client.get(
            f"{API}/admin/users",
            headers={"Authorization": f"Bearer {fresh.json()['access_token']}"},
        )
        assert allowed.status_code == 200


class TestEmailChange:
    async def test_requires_current_password(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        r = await client.patch(
            f"{API}/me",
            json={"email": "nouvelle@example.cm"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "password_required"

    async def test_changes_with_password(self, client: AsyncClient):
        await register(client)
        tokens = await login(client)
        r = await client.patch(
            f"{API}/me",
            json={"email": "nouvelle@example.cm", "current_password": GOOD["password"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["email"] == "nouvelle@example.cm"
        assert (await login(client, email="nouvelle@example.cm"))["_status"] == 200

    async def test_rejects_an_address_in_use(self, client: AsyncClient):
        await register(client, email="premiere@example.cm")
        await register(client)
        tokens = await login(client)
        r = await client.patch(
            f"{API}/me",
            json={"email": "premiere@example.cm", "current_password": GOOD["password"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 409