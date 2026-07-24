# ClosET — Identity Module

Accounts, authentication, sessions, roles and permissions.

**Verified before delivery:** 35 integration tests green against PostgreSQL 16; the Alembic migration applies, downgrades and re-applies cleanly with **zero autogenerate drift**; live smoke test through uvicorn.

## Install

```bash
pip install -r requirements.txt
cp .env.example .env.dev          # set POSTGRES_* and JWT_SECRET
alembic upgrade head
uvicorn app.main:app --reload     # interactive docs at /docs
pytest -q
```

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/register` | – | Create a customer account |
| POST | `/api/v1/auth/login` | – | Login → tokens, or a 2FA challenge |
| POST | `/api/v1/auth/login/mfa` | challenge | Submit the TOTP code |
| POST | `/api/v1/auth/login/google` | – | Google Sign-In |
| POST | `/api/v1/auth/refresh` | – | Rotate the refresh token |
| POST | `/api/v1/auth/logout` | bearer | Close one or all sessions |
| POST | `/api/v1/auth/verify-email` | – | Confirm the e-mail address |
| POST | `/api/v1/auth/forgot-password` | – | Request a reset link |
| POST | `/api/v1/auth/reset-password` | – | Set a new password |
| GET / PATCH | `/api/v1/me` | bearer | Profile + effective permissions |
| POST | `/api/v1/me/password` | bearer | Change password (revokes sessions) |
| POST / DELETE | `/api/v1/me/devices` | bearer | FCM push tokens |
| POST | `/api/v1/me/mfa/setup` · `/verify` · `/disable` | bearer | TOTP management |
| GET / POST | `/api/v1/admin/users` | `user:read:all` / `user:manage` | List / create |
| GET / PATCH / DELETE | `/api/v1/admin/users/{id}` | admin | Read / update / soft delete |
| PUT | `/api/v1/admin/users/{id}/role` | `user:manage` | Change role |
| GET | `/api/v1/admin/users/{id}/audit` | `audit:read` | Audit trail |

## Roles and permissions

Defined once in `app/modules/identity/constants.py`. Guard any route in any module:

```python
from fastapi import Depends
from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import require_permission, CurrentUser

@router.post(
    "/pieces",
    dependencies=[Depends(require_permission(Permission.CATALOGUE_WRITE))],
)
async def create_piece(user: CurrentUser): ...
```

- **customer** — browse, order, manage own account
- **sourcer** — customer permissions **plus** submissions and own payouts (a sourcer can still buy)
- **courier** — update delivery status only. Per spec §7.3 the courier normally has *no* account and acts through a signed link; this role exists if the client later wants named courier accounts
- **admin** — everything

Changing a role revokes all of that user's sessions, because permissions are embedded in the access token. `get_current_user` additionally rejects any token whose role no longer matches the database (`stale_token`), so a demotion takes effect immediately rather than at token expiry.

## Security decisions worth knowing

- **Refresh-token rotation with reuse detection.** Tokens rotate on every use and only SHA-256 hashes are stored. Presenting an already-rotated token revokes the **entire family** — the standard stolen-token signal. Covered by a test.
- **No account enumeration.** Unknown e-mail and wrong password return an identical error; `forgot-password` always returns the same message.
- **Lockout.** 5 failed attempts → 15-minute lock (`MAX_FAILED_LOGINS`, `LOCKOUT_MINUTES`).
- **Admins cannot disable 2FA** while `ADMIN_REQUIRES_2FA` is on.
- **Password change and reset revoke every session.**
- **Soft delete** for users, so orders and audit history survive; the e-mail is released for reuse.
- **Audit trail** on every sensitive action, with actor, IP and user agent.

## Notes for the rest of the build

1. `service.grant_sourcer_role()` is the hook the sourcing module calls when the administrator approves a membership.
2. Two `TODO(notifications)` markers in `router.py` mark where the verification and reset tokens should be handed to the notifications module. In `DEBUG` they are printed to the console so the flows are testable before the WhatsApp/e-mail integration exists.
3. `app/db/registry.py` must import every new module's models or Alembic will silently miss the tables.
4. The first administrator is created by promoting a registered user:
   `UPDATE users SET role='admin' WHERE email='...';` then enrol 2FA through `/me/mfa/setup`.
