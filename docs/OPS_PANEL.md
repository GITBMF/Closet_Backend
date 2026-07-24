# Internal Ops Panel (`/ops`)

A Starlette-Admin CRUD panel over the database, for engineering use during the build.

> **This is not the client deliverable.** The administrator back office promised in the requirements is the Next.js application. This panel exists so you can seed data, read raw rows and unstick records before that exists — and afterwards, as a maintenance tool.

---

## Accessing it

1. **Install the dependency** (new in `requirements.txt`):

   ```bash
   pip install -r requirements.txt
   ```

2. **Start the API** (`make dev`, `make up`, or `uvicorn app.main:app --reload`).

3. **Open** <http://localhost:8000/ops>

4. **Log in with an administrator account** — the same e-mail and password as the API. If you have no administrator yet:

   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"email":"admin@closet.cm","password":"ChangeMe2026","full_name":"Admin ClosET"}'

   make psql
   # UPDATE users SET role = 'admin' WHERE email = 'admin@closet.cm';
   ```

Only `role = 'admin'` gets in. A customer or sourcer with a valid password is refused, and the attempt is written to `audit_logs` as `ops.login_denied`.

---

## What you can see

| View | Notes |
|---|---|
| **Utilisateurs** | Full CRUD. `password_hash` and `totp_secret` are deliberately not exposed — a panel must never display a credential |
| **Sessions** | Refresh tokens, read-only. Revoke through the API so the audit trail records who did it |
| **Appareils (push)** | FCM tokens |
| **Réinitialisations** | Password-reset tokens, read-only |
| **Journal d'audit** | Append-only: no create, edit or delete. The audit trail is evidence |

As new modules land, add a `ModelView` per model in `app/ops/admin.py` — roughly three lines each.

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

When you do enable it in production, put it behind one of: a VPN, an nginx IP allow-list, or an SSH tunnel (`ssh -L 8000:localhost:8000 user@server`, which is the simplest and needs no configuration).

---

## Security model

The panel uses a **signed session cookie**, separate from the API's JWT — it is a browser tool, the app and back office are token clients.

Authorisation is re-checked on **every request**, not just at login: a demoted, disabled or soft-deleted administrator is bounced to the login screen immediately, without waiting for the cookie to expire. (Verified: demoting the account mid-session turns the next page load into a redirect.)

Sessions last 8 hours, are `SameSite=Lax`, and become `Secure`-only when `ENVIRONMENT=prod`.

Both outcomes are audited: a successful entry writes `user.logged_in` with `{"surface": "ops"}`, a refusal writes `ops.login_denied` with the offending role.

---

## Customising the look

The UI is Tabler-based and rebrandable in layers:

1. **Logo and title** — `OPS_LOGO_URL` plus the `title=` argument in `app/ops/admin.py`
2. **Colours** — drop a `custom.css` in a `statics_dir` and override the Tabler CSS variables (deep green `#1E4D2B`, gold `#C9A227`)
3. **Landing page** — pass `index_view=CustomView(...)` to render the dashboard SQL views (`v_orders_overdue`, `v_sourcer_balances`, `v_unsold_pieces`) long before the Next.js dashboard exists

Worth doing 1 and 2 (about thirty minutes) so it doesn't look like stock Tabler if the client glances at your screen. Anything beyond that is gold-plating an internal tool — the premium UI budget belongs to the contractual back office.