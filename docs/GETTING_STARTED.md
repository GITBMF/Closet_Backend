# Getting Started

Everything needed to run the ClosET backend, in whichever setup suits you.

- [Getting Started](#getting-started)
  - [1. Prerequisites](#1-prerequisites)
  - [2. First-time setup](#2-first-time-setup)
  - [3. Choose how you run it](#3-choose-how-you-run-it)
    - [Mode A — hybrid (recommended for daily work)](#mode-a--hybrid-recommended-for-daily-work)
    - [Mode B — everything in Docker](#mode-b--everything-in-docker)
    - [Mode C — fully local, no Docker](#mode-c--fully-local-no-docker)
    - [Mode D — staging / production on a VPS](#mode-d--staging--production-on-a-vps)
  - [4. Environment variables](#4-environment-variables)
  - [5. Database \& migrations](#5-database--migrations)
  - [6. Tests](#6-tests)
  - [7. Creating the first administrator](#7-creating-the-first-administrator)
  - [8. Trying the API](#8-trying-the-api)
  - [9. Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.12+ | modes A, C |
| Docker + Compose v2 | recent | modes A, B, D |
| PostgreSQL | **18** | mode C only (Docker provides it otherwise) |
| make | any | optional shortcuts |

Check what you have:

```bash
python3 --version && docker --version && docker compose version
```

> **On PostgreSQL 18.** The project targets 18. Version 16 or 17 will also run the code — nothing in the schema is 18-specific — but stay on 18 so development matches production. Note that `asyncpg < 0.31` does **not** officially support 18; the pin in `requirements.txt` already accounts for this.

---

## 2. First-time setup

```bash
git clone <repo-url> && cd Closet_Backend
cp .env.example .env.dev
```

Now edit `.env.dev` and set two values properly:

```bash
# a real password, not "change_me"
POSTGRES_PASSWORD=<something long>

# generate a real secret:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET=<paste it here>
```

`.env.dev`, `.env.staging` and `.env.prod` are git-ignored. **Never commit them.** If a credential ever reaches a commit, rotate it — assume it is public.

---

## 3. Choose how you run it

### Mode A — hybrid (recommended for daily work)

PostgreSQL in Docker, the API on your machine. Fastest reloads, and your debugger and IDE work normally.

```bash
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

docker compose --env-file .env.dev up -d postgres      # or: make db-up
alembic upgrade head
uvicorn app.main:app --reload
```

`POSTGRES_HOST` must be `localhost` in `.env.dev` for this mode (it is, by default).

Shortcut: `make dev` starts the database and the reloading server in one step.

### Mode B — everything in Docker

Closest to production; nothing but Docker required.

```bash
make up            # == docker compose --env-file .env.dev up -d --build
make logs          # follow the API logs
make down          # stop (data is preserved in the volume)
```

`docker-compose.override.yml` is applied automatically and adds development conveniences: host ports, source mounted read-only, `--reload`, `DEBUG=true`. Editing a file under `app/` reloads the container.

You do **not** need to change `POSTGRES_HOST`: the compose file injects `POSTGRES_HOST=postgres` for the API container, so the same `.env.dev` works in both mode A and mode B.

Migrations run automatically — `docker/entrypoint.sh` waits for the database, runs `alembic upgrade head`, then starts uvicorn. Set `RUN_MIGRATIONS=false` to skip that.

### Mode C — fully local, no Docker

Only if you already run PostgreSQL 18 natively.

```bash
sudo -u postgres psql -c "CREATE USER closet WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "CREATE DATABASE closet_dev OWNER closet;"

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Match `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` in `.env.dev` to what you created.

### Mode D — staging / production on a VPS

```bash
cp .env.example .env.prod        # DEBUG=false, strong secrets, real CORS_ORIGINS
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
               --env-file .env.prod up -d --build
```

Differences from development: `restart: always`, no source mount, no reload, **the database port is not published** (reach it via `make psql` or `docker compose exec`), and nginx terminates HTTP in front of the API.

Before the first real deployment: point the domain at the server, obtain a TLS certificate into `docker/nginx/certs`, add the TLS block to `docker/nginx/default.conf`, and set `CORS_ORIGINS` to the back-office origin instead of `["*"]`.

---

## 4. Environment variables

Everything is read by `app/core/config.py` through `pydantic-settings`; nothing else reads `os.environ`.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `dev` | `dev` · `staging` · `prod` |
| `DEBUG` | `false` | **must** be `false` in production |
| `POSTGRES_USER` / `_PASSWORD` / `_DB` | — | required |
| `POSTGRES_HOST` | `localhost` | `postgres` inside Docker (injected automatically) |
| `POSTGRES_PORT` | `5432` | host port in dev |
| `DB_ECHO` | `false` | log every SQL statement |
| `JWT_SECRET` | — | **required**; rotating it logs everyone out |
| `ACCESS_TOKEN_MINUTES` | `15` | access-token lifetime |
| `REFRESH_TOKEN_DAYS` | `30` | refresh-token lifetime |
| `MFA_CHALLENGE_MINUTES` | `5` | window to enter the TOTP code |
| `PASSWORD_MIN_LENGTH` | `8` | also requires letters **and** digits |
| `PASSWORD_RESET_HOURS` | `2` | reset-link validity |
| `MAX_FAILED_LOGINS` | `5` | then the account locks |
| `LOCKOUT_MINUTES` | `15` | lock duration |
| `ADMIN_REQUIRES_2FA` | `true` | administrators cannot disable TOTP |
| `TOTP_ISSUER` | `ClosET` | label shown in the authenticator app |
| `CORS_ORIGINS` | `["*"]` | restrict in production |

---

## 5. Database & migrations

**Alembic is the single source of truth for the schema.** Do not create tables by hand, and do not use `docker-entrypoint-initdb.d` — init scripts only ever run on a first-time empty volume, so they cannot evolve a database that already holds data.

```bash
alembic upgrade head                          # apply everything
alembic revision --autogenerate -m "message"  # after changing models
alembic downgrade -1                          # roll back one step
alembic current                               # where am I?
alembic history --verbose                     # what exists
```

After adding a model, import it in **`app/db/registry.py`**. If you forget, autogenerate cannot see the table — and may generate a `DROP` for it.

Always read a generated migration before committing it. Autogenerate does not detect table or column renames (it emits drop + create, which loses data), server-default changes, or `CHECK` constraints.

Start over from scratch:

```bash
make reset-db      # drops the docker volume, recreates, re-migrates
```

---

## 6. Tests

The suite runs against a **real PostgreSQL** database — no SQLite substitute, because the schema uses PostgreSQL enums, `JSONB` and `INET`.

```bash
docker compose --env-file .env.dev up -d postgres   # database must be running
pytest -q                                            # 34 tests
pytest -q tests/test_identity.py::TestRBAC           # one class
pytest -q -k "mfa" -v                                # by keyword
```

The suite creates its schema, truncates between tests and cleans up after itself. It uses the database named in `.env.dev`, so point it at a scratch database if you keep data you care about.

Inside Docker: `docker compose exec api pytest -q`.

---

## 7. Creating the first administrator

There is no bootstrap endpoint by design — promoting a user is a deliberate, audited act.

```bash
# 1. register normally (through /docs, the app, or curl)
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@closet.cm","password":"ChangeMe2026","full_name":"Admin ClosET"}'

# 2. promote
make psql
# then:
UPDATE users SET role = 'admin' WHERE email = 'admin@closet.cm';
```

Log in again (the old token carries the old role and is now rejected as `stale_token`), then enable two-factor authentication immediately via `POST /api/v1/me/mfa/setup` and `/me/mfa/verify`. With `ADMIN_REQUIRES_2FA=true` an administrator cannot switch it off afterwards.

---

## 8. Trying the API

Open <http://localhost:8000/docs> for the interactive reference, or:

```bash
# health
curl http://localhost:8000/health

# register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"awa@example.cm","password":"Dressing2026","full_name":"Awa K"}'

# login -> access_token + refresh_token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"awa@example.cm","password":"Dressing2026"}'

# authenticated call
curl http://localhost:8000/api/v1/me -H "Authorization: Bearer <access_token>"
```

---

## 9. Troubleshooting

**`no such file or directory ... /var/lib/postgresql/data` after switching to PostgreSQL 18**
PostgreSQL 18 moved `PGDATA` to `/var/lib/postgresql/18/docker` and the image's `VOLUME` to `/var/lib/postgresql`. A volume mounted at the old `/var/lib/postgresql/data` either fails to start or is silently ignored — the container then initialises an empty database and your data appears to have vanished. `docker-compose.yml` already targets the correct path. If you have an old `postgres_data` volume or the `./db_closet` bind mount from the previous setup, they hold PostgreSQL 16 files that 18 cannot read: dump first if the data matters (`pg_dumpall`), otherwise `docker compose down -v` and re-migrate.

**`connection refused` on port 5432**
The database is not running (`make db-up`), or something else already owns the port. Change `POSTGRES_PORT` in `.env.dev` — it only affects the host side.

**`password authentication failed`**
The volume was initialised with different credentials; `POSTGRES_PASSWORD` only takes effect on a *first* start. `make reset-db`, or change the password inside the running container.

**API in Docker cannot reach the database**
Inside a container the host is `postgres`, not `localhost`. Compose injects this; if you overrode `POSTGRES_HOST` in `.env.dev`, remove it.

**`AttributeError: module 'bcrypt' has no attribute '__about__'`**
`bcrypt` 4.1+ broke passlib's version probe. `requirements.txt` pins `bcrypt==4.0.1`; reinstall.

**Tests fail with `type "user_role" does not exist`**
The enum types are created by the migration, and mirrored by the test fixture. Run against a database created by `alembic upgrade head`, or let the fixture build the schema in an empty database.

**Autogenerate wants to drop tables you did not touch**
A model is missing from `app/db/registry.py`.

**`codebase.txt` keeps growing / contains copies of itself**
`pip install pathspec` (already in `requirements.txt`) so the export honours `.gitignore`, and delete the committed `codebase.txt`.

**Port 8000 already in use**
`API_PORT=8001` in `.env.dev`, or `uvicorn --port 8001`.