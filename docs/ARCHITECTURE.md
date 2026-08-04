# ClosET Backend — Architecture & Folder Structure

**Status:** adopted — this is how the codebase is organised
**Applies to:** `Closet_Backend` (FastAPI · PostgreSQL · Docker)
**Related docs:** `SCHEMA_NAMING.md`, `closet_erd.svg`, `TEAM_WORK_SPLIT.md` (Week 0)

---

## 1. Why this document exists

The repository began as infrastructure only. It now holds the identity, geo, delivery-pricing and catalogue modules built on this structure, with the full schema migrated. The structure below was chosen at the cheapest possible moment — before feature code — and has held up as modules landed.

The structure below is **package-by-feature** (a folder per business domain), not package-by-layer (a folder per technical role). The reason is scale. The database design has 44 tables across 14 modules. In a layer-first tree, `models/` eventually holds 44 files, `schemas/` holds 44 more, and adding one field to *pieces* means editing four directories that each contain everything. In a feature-first tree, that change happens inside `modules/catalogue/` and nowhere else.

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
│   │   ├── storage/                   # ✅ S3-compatible media storage (swappable: MinIO/S3/R2)
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
│   │   └── fcm/
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
│   ├── GETTING_STARTED.md             # setup for every environment
│   ├── OPS_PANEL.md                   # the internal /ops admin panel
│   ├── SCHEMA_NAMING.md               # the 44-table naming reference
│   └── closet_erd.svg                 # the entity-relationship diagram
│
├── .env.example                       # committed — the template, no real values
├── requirements.txt                   # pinned runtime + dev dependencies
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

## 6. History — the migration into this structure (completed)

The repository began as an infrastructure skeleton with a different shape. The move into this structure is **done**; this section is kept as a record of what changed and why.

The schema now lives entirely in Alembic (`alembic/versions/`), not in any `docker-entrypoint-initdb.d` SQL. Bootstrapping the schema through init-scripts works exactly once — on an empty volume — and cannot evolve a database that already has data, so it was replaced by migrations. The container entrypoint runs `alembic upgrade head` at start, and dev, staging and production converge on the same command. Two migrations (`0001_identity`, `0002_must_change_password`) build identity; `0003_full_schema` builds the remaining 44-table schema. The earlier competing SQL drafts (`items`/`selections` vs `pieces`/`purchase`) were resolved in favour of the singular-naming design recorded in `SCHEMA_NAMING.md`.

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

## 9. Findings from the initial repository (all resolved)

These were noted while reading the original export and have since been fixed. Kept as a record.

1. **Environment files were tracked by git** (named `env.dev` without a leading dot, so `.gitignore` missed them). Renamed to `.env.*`; `.gitignore` root-anchors them now.
2. **`requirements.txt` had one line.** The full pinned set (fastapi, uvicorn, sqlalchemy, alembic, asyncpg, pydantic-settings, python-jose, passlib, httpx, boto3, …) is now pinned and verified from a clean venv.
3. **CI installed dependencies and stopped.** It now runs ruff + tests against a real Postgres service and builds the Docker image.
4. **`docker-compose.yml` had no `api` service** and bind-mounted the database inside the repo. It now has `api`, `minio`, and `minio_init` services on named volumes (`db_closet`, `minio_data`).
5. **`codebase.txt` was committed** and re-exported into itself; it is now git-ignored.
6. **`READme.md` → `README.md`** (Linux is case-sensitive).