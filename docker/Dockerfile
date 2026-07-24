# syntax=docker/dockerfile:1
# Multi-stage build.
#   target dev     -> includes pytest/ruff, runs as root-less user, hot reload
#   target runtime -> slim production image
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# libpq is needed by psycopg2 (Alembic's sync driver)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*


# ----------------------------------------------------------------- builder
FROM base AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt


# ----------------------------------------------------------------- runtime
FROM base AS runtime

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# never run the API as root
RUN useradd --create-home --uid 10001 closet

COPY --chown=closet:closet app ./app
COPY --chown=closet:closet alembic ./alembic
COPY --chown=closet:closet alembic.ini ./
COPY --chown=closet:closet docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER closet
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# --------------------------------------------------------------------- dev
FROM runtime AS dev

USER root
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt
COPY --chown=closet:closet tests ./tests
COPY --chown=closet:closet pytest.ini ./
USER closet