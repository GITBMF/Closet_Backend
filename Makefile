# ClosET backend — common tasks.  `make help` lists everything.
ENV_FILE ?= .env.dev
COMPOSE  := docker compose --env-file $(ENV_FILE)

.DEFAULT_GOAL := help
.PHONY: help install db-up db-down dev up down restart logs ps build \
        migrate revision downgrade reset-db psql db-dump check-eol shell \
        admin-create admin-list admin-promote admin-password admin-reset-mfa \
        test lint fmt clean

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	 | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- local dev
install:  ## create .venv and install dependencies
	python3 -m venv .venv && ./.venv/bin/pip install --upgrade pip \
	 && ./.venv/bin/pip install -r requirements.txt

db-up:  ## start ONLY postgres (for running the API on the host)
	$(COMPOSE) up -d postgres

db-down:  ## stop postgres
	$(COMPOSE) stop postgres

dev: db-up  ## run the API on the host with hot reload
	uvicorn app.main:app --reload --port 8000

# ------------------------------------------------------------- full docker
up:  ## start the whole stack in docker
	$(COMPOSE) up -d --build

down:  ## stop the stack (data is kept)
	$(COMPOSE) down

restart:  ## rebuild and restart the api container
	$(COMPOSE) up -d --build api

logs:  ## follow the api logs
	$(COMPOSE) logs -f api

ps:  ## container status
	$(COMPOSE) ps

build:  ## build the images without starting
	$(COMPOSE) build

# ------------------------------------------------------------- migrations
migrate:  ## apply migrations (host)
	alembic upgrade head

revision:  ## autogenerate a migration:  make revision m="add pieces"
	alembic revision --autogenerate -m "$(m)"

downgrade:  ## roll back one migration
	alembic downgrade -1

reset-db:  ## DESTRUCTIVE: drop the volume and re-migrate
	$(COMPOSE) down -v && $(COMPOSE) up -d postgres && sleep 5 && alembic upgrade head

# ------------------------------------------------------------------ shells
admin-create:  ## create the first administrator (interactive)
	$(COMPOSE) exec api python scripts/manage_admin.py create

admin-list:  ## list administrators
	$(COMPOSE) exec api python scripts/manage_admin.py list

admin-promote:  ## promote an account:  make admin-promote e=user@closet.cm
	$(COMPOSE) exec api python scripts/manage_admin.py promote --email "$(e)"

admin-password:  ## reset a password:  make admin-password e=user@closet.cm
	$(COMPOSE) exec api python scripts/manage_admin.py set-password --email "$(e)"

admin-reset-mfa:  ## clear 2FA:  make admin-reset-mfa e=user@closet.cm
	$(COMPOSE) exec api python scripts/manage_admin.py reset-mfa --email "$(e)"

psql:  ## open psql inside the database container
	# Read the credentials from the container's own environment. Parsing
	# $(ENV_FILE) here used to break on CRLF line endings: the trailing \r
	# ended up inside the role name.
	$(COMPOSE) exec postgres sh -c 'exec psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

db-dump:  ## dump the database to backup.sql
	$(COMPOSE) exec -T postgres sh -c 'exec pg_dump -U "$$POSTGRES_USER" "$$POSTGRES_DB"' > backup.sql
	@echo "wrote backup.sql"

check-eol:  ## fail if any shell script or env file has CRLF line endings
	@cr=$$(printf '\r'); \
	bad=$$(find . -type f \( -name '*.sh' -o -name '.env*' -o -name 'Makefile' \) \
	       -not -path './.git/*' -not -path './.venv/*' -print0 \
	       | xargs -0 grep -Il "$$cr" 2>/dev/null); \
	if [ -n "$$bad" ]; then \
	  echo "CRLF line endings found in:"; echo "$$bad" | sed 's/^/  /'; \
	  echo "fix with:  sed -i 's/\r$$//' <file>"; exit 1; \
	else echo "line endings OK"; fi

shell:  ## shell inside the api container
	$(COMPOSE) exec api sh

# ------------------------------------------------------------------ checks
test:  ## run the test suite (needs postgres up)
	pytest -q

lint:  ## ruff
	ruff check app tests

fmt:  ## ruff --fix + format
	ruff check --fix app tests && ruff format app tests

clean:  ## remove caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} + ; \
	rm -rf .pytest_cache .ruff_cache .mypy_cache