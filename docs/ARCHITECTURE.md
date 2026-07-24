# ClosET Backend — Architecture & Folder Structure

**Status:** proposal for adoption before feature code is written
**Applies to:** `Closet_Backend` (FastAPI · PostgreSQL · Docker)
**Related docs:** `DB_DESIGN.md`, `closet_schema.sql`, UML pack (Week 0)

---

## 1. Why this document exists

The repository currently holds infrastructure only — `docker-compose.yml`, `init1.sql`, environment files, a CI skeleton. No application code has been written yet. This is the cheapest possible moment to choose a structure: after Sprint 1, moving files means moving imports, migrations and tests too.

The structure below is **package-by-feature** (a folder per business domain), not package-by-layer (a folder per technical role). The reason is scale. The database design has 43 tables across 14 modules. In a layer-first tree, `models/` eventually holds 43 files, `schemas/` holds 43 more, and adding one field to *pieces* means editing four directories that each contain everything. In a feature-first tree, that change happens inside `modules/catalogue/` and nowhere else.

This also mirrors the modular monolith described in the requirements spec (§10) — the same boundaries, expressed in the filesystem.

---

## 2. Guiding principles

1. **A module owns its tables.** Anything about orders lives in `modules/orders/`. If you can't decide where something goes, it probably belongs to the module that owns the data it touches.
2. **Layers flow one way:** `router → service → repository → models`. A router never touches a repository. A service never imports a router. No exceptions — this is what keeps the import graph acyclic.
3. **Modules talk through services, never through each other's repositories.** `orders` may call `payments_service.initiate()`; it may not query the `payments` table directly.
4. **Integrations are dumb.** `integrations/cinetpay/` speaks HTTP and maps payloads. It contains no business rules — deciding *when* to refund is `modules/payments/service.py`'s job. This is what makes swapping CinetPay for direct MTN MoMo later a contained change.
5. **`core/` holds no business logic.** Config, database session, security primitives, shared dependencies, error mapping. If it mentions a piece, an order or a sourcer, it doesn't belong there.
6. **Tests mirror the module tree.** `tests/unit/orders/` next to `app/modules/orders/`. Anyone can find the test for a file in two seconds.
7. **One version, one router.** All routes assemble in `app/api/router.py` under `/api/v1`. When `/api/v2` arrives, it is a second assembly file, not a fork of the modules.

---

## 3. The structure

```text
closet-backend/
│
├── .github/
│   └── workflows/
│       ├── ci.yml                     # lint + type-check + tests (on every push)
│       └── deploy.yml                 # build image + deploy (on main / tags)
│
├── alembic/
│   ├── versions/                      # one file per migration, committed
│   ├── env.py                         # imports app.db.registry so autogenerate sees all models
│   └── script.py.mako
├── alembic.ini
│
├── app/
│   ├── __init__.py
│   ├── main.py                        # create_app() factory, lifespan, middleware, router mount
│   │
│   ├── core/                          # cross-cutting plumbing — NO business logic
│   │   ├── config.py                  # pydantic-settings: one Settings class, env-driven
│   │   ├── database.py                # async engine, sessionmaker, declarative Base
│   │   ├── security.py                # JWT issue/verify, password hashing, TOTP, link signing
│   │   ├── dependencies.py            # get_db, get_current_user, require_role, get_pagination
│   │   ├── exceptions.py              # AppError hierarchy + handler mapping to HTTP
│   │   ├── pagination.py
│   │   ├── logging.py                 # structured logging + request id
│   │   └── constants.py               # enums shared across modules (Currency, ActorType)
│   │
│   ├── db/
│   │   ├── base.py                    # Base + common mixins (UUIDPk, Timestamped, SoftDelete)
│   │   └── registry.py                # imports every module's models — Alembic's entry point
│   │
│   ├── api/
│   │   ├── router.py                  # includes every module router under /api/v1
│   │   └── health.py                  # /health, /ready — used by Docker and monitoring
│   │
│   ├── modules/                       # <-- ONE FOLDER PER BUSINESS DOMAIN
│   │   ├── identity/                  # users, auth, refresh tokens, 2FA, audit log
│   │   ├── geo/                       # regions, divisions, subdivisions, cities, neighbourhoods
│   │   ├── catalogue/                 # pieces, media, houses, universes, wishlist, publication
│   │   ├── orders/                    # orders, items, status workflow, reservation lock
│   │   ├── payments/                  # payments, events, refunds, reconciliation
│   │   │   └── providers/             # base.py (Protocol), cinetpay.py, mtn_momo.py …
│   │   ├── delivery/                  # pricing grid, deliveries, courier links, events
│   │   ├── sourcing/                  # sourcer profiles, submissions, payouts, entrust requests
│   │   ├── privileges/                # privilege codes + redemptions
│   │   ├── showcasing/                # sponsors, featured slots
│   │   ├── returns/                   # return tickets, restocking
│   │   ├── notifications/             # templates, dispatch, channel routing
│   │   └── dashboard/                 # admin KPI + alert queries (reads the SQL views)
│   │
│   ├── integrations/                  # thin clients for the outside world
│   │   ├── cinetpay/                  # client.py, signatures.py, schemas.py
│   │   ├── whatsapp/                  # Business API client + template registry
│   │   ├── email/
│   │   ├── fcm/
│   │   └── storage/                   # S3-compatible upload + CDN URL building
│   │
│   ├── workers/                       # anything not in the request/response cycle
│   │   ├── scheduler.py               # periodic: expire reservations, retry notifications
│   │   └── tasks/                     # one file per job family
│   │
│   └── ops/                           # Starlette-Admin internal panel — NOT the client back office
│       ├── admin.py                   # Admin() instance, mounted at /ops
│       ├── auth.py                    # AuthProvider (separate credentials from the API)
│       ├── views/                     # one ModelView module per domain
│       ├── templates/                 # ClosET branding overrides
│       └── statics/
│
├── tests/
│   ├── conftest.py                    # test DB, async client, transaction rollback per test
│   ├── factories/                     # object mothers per module
│   ├── unit/                          # services in isolation, no DB
│   ├── integration/                   # routers + real test DB
│   └── e2e/                           # full journeys: guest checkout → webhook → tracking
│
├── scripts/
│   ├── seed_geo.py                    # load regions/divisions/subdivisions reference data
│   ├── seed_demo.py                   # demo catalogue for the Saturday demos
│   ├── export_codebase.py             # (currently parse.py at the root)
│   └── backup_db.sh
│
├── docker/
│   ├── Dockerfile                     # multi-stage, non-root user
│   ├── Dockerfile.dev
│   ├── entrypoint.sh                  # waits for DB → alembic upgrade head → uvicorn
│   └── nginx/
│       └── default.conf
├── docker-compose.yml                 # base: db + api
├── docker-compose.override.yml        # local dev: hot reload, exposed ports
├── docker-compose.prod.yml            # VPS: nginx, restart policies, no exposed DB port
│
├── docs/
│   ├── ARCHITECTURE.md                # this file
│   ├── DB_DESIGN.md
│   ├── uml/                           # Week 0 diagram sources (.puml) + exports
│   └── adr/                           # short decision records (see §8)
│
├── .env.example                       # committed — the template, no real values
├── requirements/
│   ├── base.txt                       # runtime
│   ├── dev.txt                        # -r base.txt + pytest, ruff, mypy
│   └── prod.txt                       # -r base.txt + gunicorn
├── Makefile                           # make up / make test / make migrate / make lint
├── README.md
└── .gitignore
```

---

## 4. Anatomy of a module

Every folder under `app/modules/` has the same shape. Learn it once, apply it eleven times:

```text
modules/orders/
├── __init__.py
├── models.py          # SQLAlchemy models — the tables this module owns
├── schemas.py         # Pydantic request/response contracts
├── router.py          # HTTP layer only: parse, authorize, delegate, serialize
├── service.py         # business rules — the module's real value
├── repository.py      # database access; the ONLY place raw queries live
├── dependencies.py    # FastAPI dependencies specific to this module
├── exceptions.py      # OrderNotFound, PieceAlreadyReserved …
├── constants.py       # module enums and literals
└── tasks.py           # background jobs owned by this module (optional)
```

Not every module needs every file — `geo/` may never have `tasks.py`. Add files when they earn their place, but don't invent new names: consistency is the point.

**Where a workflow lives, concretely.** Guest checkout touches four modules: `catalogue` (reserve the piece), `orders` (create the order), `privileges` (validate the code), `payments` (initiate). The orchestration belongs to `orders/service.py`, which calls the other three *services*. No router calls another router; no service reaches into another module's repository.

---

## 5. "Where do I put this?" — quick reference

| What you're adding | Where it goes |
|---|---|
| A new endpoint | `modules/<domain>/router.py` |
| A business rule | `modules/<domain>/service.py` |
| A SQL query | `modules/<domain>/repository.py` |
| A new table | `modules/<domain>/models.py` + Alembic migration |
| A request/response shape | `modules/<domain>/schemas.py` |
| A call to CinetPay | `integrations/cinetpay/` (transport) + `modules/payments/` (rules) |
| A new payment provider | `modules/payments/providers/<name>.py` implementing the base Protocol |
| A WhatsApp template | `integrations/whatsapp/templates.py` + `notification_templates` row |
| A scheduled job | `workers/tasks/` + registration in `workers/scheduler.py` |
| A shared enum used by 3 modules | `core/constants.py` |
| An admin CRUD screen | `ops/views/<domain>.py` |
| A KPI query for the dashboard | `modules/dashboard/repository.py` (reads the SQL views) |
| A one-off data fix | `scripts/` — never a hidden endpoint |

---

## 6. Migration from the current repository

The current tree is small, so this is a one-afternoon move — do it before Sprint 1 code lands.

| Today | Target | Note |
|---|---|---|
| `parse.py` (root) | `scripts/export_codebase.py` | tooling doesn't belong at the root |
| `init1.sql` | `alembic/versions/0001_initial.py` | see below — this is the important one |
| `env.dev` / `env.staging` / `env.prod` | `.env.dev` / `.env.staging` / `.env.prod` | **currently tracked by git — see §9** |
| `docker-compose.yml` | same + `docker/` folder, override files | add the `api` service; nginx in the prod file |
| `requirements.txt` | `requirements/base.txt` + `dev.txt` | currently one line: `fastapi` |
| `Instructions_backend.md` | `README.md` (dev setup section) | one entry point for onboarding |
| `codebase.txt` | delete, and keep it ignored | it was re-exported into itself |
| `READme.md` | `README.md` | case matters on Linux servers |

**On `init1.sql`.** Bootstrapping the schema through `docker-entrypoint-initdb.d` works exactly once — on an empty volume. It cannot evolve a database that already has data, which means the first schema change on the VPS becomes a manual `psql` session. Move the schema into Alembic now, while the only cost is one migration file, and keep `init1.sql` for nothing more than `CREATE EXTENSION`. The container entrypoint then runs `alembic upgrade head` at start, and dev, staging and production converge on the same command.

**On the schema itself.** `init1.sql` and `closet_schema.sql` model the same business differently (`items` vs `pieces`, `selections` vs `orders`, `role INT 1-4` vs enum + separate sourcer profile, and no tables yet for payments, deliveries, notifications or payouts). Both are defensible; what is not defensible is starting to write services against one while migrations are generated from the other. Pick one at the next validation meeting, record the choice in `docs/adr/`, and generate the first migration from it.

---

## 7. Scaling path

The structure is designed so that growth is additive, never structural:

- **More features** → new folders under `modules/`. Nothing existing moves.
- **More developers** → module ownership maps to people; merge conflicts stay inside a module instead of in a shared `models.py`.
- **More traffic** → `workers/` already separates async work; the API can be replicated behind nginx without touching the code layout.
- **A module outgrows the monolith** → because its router, service, repository and models are already one folder with an explicit service boundary, extracting it into its own deployable is a packaging exercise, not a rewrite. *Do not do this preemptively* — the spec's scale does not justify microservices, and the CI workflow's current name ("Tests on Microservices") describes an architecture the project does not have.
- **A second API version** → `api/v2/` assembles the same module routers with new schemas.

---

## 8. Conventions

- **Imports:** absolute from `app.` — `from app.modules.orders.service import OrderService`. No relative imports beyond a single dot inside a module.
- **Async everywhere:** async SQLAlchemy session, async HTTP client. One blocking call in a request path stalls the event loop for every concurrent user.
- **Alembic autogenerate:** every model must be imported by `app/db/registry.py`, or the migration will silently drop the table.
- **Naming:** modules are lowercase and plural where they hold collections (`orders`, `payments`, `returns`); tables stay as defined in the DB design; Python names in English, even though the product UI is French — never mix the two inside one identifier.
- **French UI strings** live in one place (per the spec's brand-vocabulary requirement), not scattered through services.
- **Decision records:** any choice a future developer might reverse by accident gets a five-line file in `docs/adr/` — payment aggregator, admin panel, schema source of truth, deployment target.

---

## 9. Findings in the current repository

Noted while reading the export; all are quick fixes, listed hardest-consequence first.

1. **The environment files are tracked by git.** `.gitignore` excludes `.env` and `.env.*`, but the files are named `env.dev`, `env.staging`, `env.prod` — no leading dot — so they don't match, and they contain database credentials. `Instructions_backend.md` refers to them *with* the dot, so this looks like an accidental rename. Rename them, confirm with `git status`, and treat any credential that has been in a commit as compromised: rotate it. Purging git history is only worth it if the repository is or will be public.
2. **`requirements.txt` contains one line** (`fastapi==0.139.2`) — no `uvicorn`, `sqlalchemy`, `alembic`, `asyncpg`, `pydantic-settings`, `python-jose`, `passlib`, `httpx`. Pin the real set now, split base/dev, and the CI cache starts working.
3. **CI installs dependencies and stops.** No lint, no type check, no tests, no service container for Postgres — so a red build is currently impossible. Add `ruff`, `mypy` and `pytest` steps with a `postgres:16` service; a pipeline that can't fail provides no signal.
4. **`docker-compose.yml` has no `api` service** and no nginx, though the README describes three containers. Also: the database bind-mounts `./db_closet` *inside the repository* while a named `postgres_data` volume is declared and unused. Switch to the named volume — a stray `git add .` should never be able to stage the database, and bind-mounted PGDATA has permission quirks across machines.
5. **`codebase.txt` was committed**, so the export ended up containing an older copy of itself (the duplicated file entries in the dump). The provided `.gitignore` already excludes it; the nesting also indicates `pathspec` isn't installed locally, so `.gitignore` rules were skipped during the export — `pip install pathspec` fixes both.
6. **`READme.md` → `README.md`.** Linux is case-sensitive; tooling and forges look for the canonical name.

---

## 10. Adoption checklist

- [ ] Rename `env.*` → `.env.*`, verify with `git status`, rotate the exposed credentials
- [ ] Create the folder skeleton (`scaffold_backend.py`)
- [ ] Move `parse.py` → `scripts/`, delete committed `codebase.txt`, rename `READme.md`
- [ ] Decide the schema source of truth; record it in `docs/adr/0001-schema-source.md`
- [ ] Generate `alembic/versions/0001_initial.py`; reduce `init1.sql` to extensions only
- [ ] Fill `requirements/base.txt` and `dev.txt`
- [ ] Add the `api` service to compose + `entrypoint.sh` running `alembic upgrade head`
- [ ] Extend CI: ruff + mypy + pytest against a `postgres:16` service container
- [ ] Merge `Instructions_backend.md` into `README.md`