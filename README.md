# ClosET — Backend API

Backend for **ClosET · L'élégance durable** — a premium second-hand fashion platform (Cameroon).
FastAPI · PostgreSQL 18 · SQLAlchemy 2 (async) · Alembic · S3-compatible object storage · Docker.

The API serves three clients: the Flutter application (customer + sourcer areas), the Next.js administrator back office, and the courier's signed-link page.

---

## Quick start

Two commands, if you have Docker:

```bash
cp .env.example .env.dev        # then edit POSTGRES_PASSWORD and JWT_SECRET
make up
```

The API is on <http://localhost:8000>, interactive documentation on <http://localhost:8000/docs>. `make up` also starts **MinIO** (object storage for images) on <http://localhost:9000>, with its console on <http://localhost:9001>.

Not using `make`? See **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)** — it covers every setup mode (hybrid, full Docker, fully local), migrations, tests, creating the first administrator, and troubleshooting.

---

## What is implemented

| Module | Status |
|---|---|
| **identity** — accounts, login, sessions, 2FA, roles & permissions, audit log | ✅ done ([details](README_IDENTITY.md)) |
| **geo** — regions, divisions, subdivisions, delivery-zone cities & neighbourhoods | ✅ done |
| **delivery-pricing** — the quote engine (city → region → quote-required) and rate management | ✅ done |
| **catalogue** — pieces, media upload, houses/universes, wishlist, search, publication batches | ✅ done |
| orders · payments · delivery · sourcing · privileges · showcasing · returns · notifications · dashboard | planned |

The full 44-table schema for **all** modules is already migrated (`alembic/versions/0003_full_schema.py`), so every developer builds against stable, shared tables. The modules above marked *planned* have their models in place; what remains is each module's router/service/repository.

Authentication is **e-mail + password**, with optional TOTP two-factor (mandatory for administrators). Google Sign-In and e-mail verification are deliberately **not** in this version.

Product **images** are stored in S3-compatible object storage (MinIO in development; AWS S3 / Cloudflare R2 in production) behind a swappable provider interface — the client uploads a file and the backend generates and stores the URL.

---

## Project structure

```text
app/
  core/         config, database session, security primitives, error mapping
  core/storage/ swappable object-storage providers (S3/MinIO) for media
  db/           declarative base, mixins, model registry for Alembic
  api/          router assembly under /api/v1
  modules/      one folder per business domain (identity, catalogue, orders, …)
alembic/        migrations — the single source of truth for the schema
docker/         Dockerfile, entrypoint, nginx
docs/           architecture and setup guides
tests/          mirrors the module tree
```

Each module follows the same shape: `models · schemas · router · service · repository · dependencies · exceptions · constants`. The rule that keeps it navigable: **router → service → repository → models**, one direction only, and modules talk to each other through *services*, never through another module's repository.

Full rationale in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Everyday commands

```bash
make help          # list every task
make dev           # postgres in docker, API on the host with hot reload
make up            # whole stack in docker
make logs          # follow the API logs
make migrate       # alembic upgrade head
make revision m="add pieces table"
make test          # pytest
make lint          # ruff
make psql          # psql inside the database container
make reset-db      # DESTRUCTIVE: wipe the volume and re-migrate
```

---

## Conventions

- **Alembic owns the schema.** Never create tables by hand or through `docker-entrypoint-initdb.d`; write a migration. Every new model must be imported in `app/db/registry.py` or autogenerate will miss it — or worse, emit a `DROP`.
- **Async everywhere.** One blocking call in a request path stalls the event loop for every concurrent user.
- **Code and identifiers in English; user-facing strings in French** (the product's brand vocabulary is contractual — see the requirements spec §8.1). Never mix the two inside one identifier.
- **Secrets live in `.env.*`, which is git-ignored.** `.env.example` is the committed template. If a credential ever lands in a commit, rotate it.
- **Every sensitive action writes to `audit_logs`** with actor, IP and user agent.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Setup for every environment, migrations, tests, troubleshooting |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Folder structure and the reasoning behind it |
| [README_IDENTITY.md](README_IDENTITY.md) | Identity module: endpoints, roles, security decisions |
| `/docs` (running app) | Generated OpenAPI reference |