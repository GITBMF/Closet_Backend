# Internal Ops Panel (`/ops`)

A [Starlette-Admin](https://jowilf.github.io/starlette-admin/) CRUD panel over the database, for engineering use during the build.

> **This is not the client deliverable.** The administrator back office promised in the requirements is the Next.js application. This panel exists so you can seed data, read raw rows and unstick records before that exists — and afterwards, as a maintenance tool.

---

## Accessing it

1. **Install the dependency** (already in `requirements.txt`):

   ```bash
   pip install -r requirements.txt
   ```

2. **Start the API** — `make dev`, `make up`, or `uvicorn app.main:app --reload`.

3. **Open** <http://localhost:8000/ops>

4. **Log in with an administrator account** — the same e-mail and password as the API.

If you have no administrator yet, see [Creating administrators](GETTING_STARTED.md#7-creating-administrators): either set `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` before the first launch, or run `python scripts/manage_admin.py create`.

### A freshly bootstrapped admin cannot log in here yet

An account created by the bootstrap (or reset by `manage_admin.py`) carries the `must_change_password` flag. The panel **refuses** it:

> Changez votre mot de passe via l'API avant d'accéder au panneau.

That is deliberate. The bootstrap password lives in an environment file, in your deployment history and probably in a chat message, so the API restricts such an account to `/me` and `/me/password`. If the panel accepted it, that restriction would be worthless — the same credential would grant full database CRUD. Change the password first:

```bash
curl -X POST http://localhost:8000/api/v1/me/password \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"current_password":"<bootstrap password>","new_password":"<your own>"}'
```

Then log in to `/ops` normally.

---

## What you can see

| View | Notes |
|---|---|
| **Utilisateurs** | Full CRUD, including `role`, `is_active` and `must_change_password`. `password_hash` and `totp_secret` are deliberately absent — a panel must never display a credential |
| **Sessions** | Refresh tokens, read-only. Revoke through the API or the CLI so the audit trail records who did it |
| **Appareils (push)** | FCM tokens |
| **Réinitialisations** | Password-reset tokens, read-only |
| **Journal d'audit** | Append-only: no create, edit or delete. The audit trail is evidence |

Ticking `must_change_password` on a user is a quick way to force them to re-set their password at next login — and it locks them out of this panel until they do.

As new modules land, add a `ModelView` per model in `app/ops/admin.py` — about three lines each.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPS_ENABLED` | `true` | mount the panel at all |
| `OPS_ALLOW_IN_PROD` | `false` | second guard, see below |
| `OPS_BASE_URL` | `/ops` | change the path |
| `OPS_SESSION_SECRET` | *(falls back to `JWT_SECRET`)* | cookie signing key |
| `OPS_LOGO_URL` | *(empty)* | ClosET logo on the login screen and header |

### Production

Set `OPS_ENABLED=false` in `.env.prod`. If you genuinely need it on a server, the app **refuses to start** with `OPS_ENABLED=true` unless `OPS_ALLOW_IN_PROD=true` is also set — a deliberate speed bump, because a database CRUD panel on a public host is a standing invitation.

When you do enable it in production, put it behind one of: a VPN, an nginx IP allow-list, or an SSH tunnel — the last needs no configuration at all:

```bash
ssh -L 8000:localhost:8000 user@server
# then browse to http://localhost:8000/ops
```

---

## Security model

The panel uses a **signed session cookie**, separate from the API's JWT — it is a browser tool, while the app and back office are token clients.

Authorisation is re-checked on **every request**, not just at login. Three conditions must hold each time: the account still exists and is active, its role is still `admin`, and `must_change_password` is not set. So a demotion, a deactivation, or a CLI password reset takes effect on the next page load rather than when the cookie expires. (Verified: demoting an account mid-session turns the next request into a redirect to the login screen.)

Sessions last 8 hours, are `SameSite=Lax`, and become `Secure`-only when `ENVIRONMENT=prod`.

Both outcomes are audited: a successful entry writes `user.logged_in` with `{"surface": "ops"}`; a refusal by a non-administrator writes `ops.login_denied` with the offending role. A wrong password produces a generic message and reveals nothing about whether the address exists.

---

## Customising the look

The UI is Tabler-based and rebrandable in layers:

1. **Logo and title** — `OPS_LOGO_URL` plus the `title=` argument in `app/ops/admin.py`
2. **Colours** — drop a `custom.css` in a `statics_dir` and override the Tabler CSS variables (deep green `#1E4D2B`, gold `#C9A227`)
3. **Landing page** — pass `index_view=CustomView(...)` to render the dashboard SQL views (`v_orders_overdue`, `v_sourcer_balances`, `v_unsold_pieces`) long before the Next.js dashboard exists

Worth doing 1 and 2 (about thirty minutes) so it doesn't look like stock Tabler if the client glances at your screen. Anything beyond that is gold-plating an internal tool — the premium UI budget belongs to the contractual back office.

---

## Troubleshooting

**"Changez votre mot de passe via l'API…"** — expected for a bootstrap or freshly reset account; see above.

**"Accès réservé aux administrateurs"** — the credentials are correct but the role is not `admin`. Check with `python scripts/manage_admin.py list`.

**Redirected to the login screen on every click** — the session cookie is being rejected. Either the account was demoted, deactivated or flagged for a password change while you were logged in, or `OPS_SESSION_SECRET` / `JWT_SECRET` changed since the cookie was issued (which invalidates every session).

**404 on `/ops`** — `OPS_ENABLED` is false, or `OPS_BASE_URL` was changed.

**The app refuses to start, mentioning `OPS_ALLOW_IN_PROD`** — `ENVIRONMENT=prod` with the panel enabled. Either set `OPS_ENABLED=false`, or acknowledge the risk with `OPS_ALLOW_IN_PROD=true` once access is restricted.