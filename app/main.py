"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import register_exception_handlers
from app.modules.identity.bootstrap import ensure_bootstrap_admin
from app.ops.admin import mount_ops


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Creates the first administrator when configured; no-op otherwise.
    await ensure_bootstrap_admin()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ClosET API",
        version="1.0.0",
        description="Backend ClosET — L'élégance durable",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # internal engineering panel — NOT the client back office
    mount_ops(app)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    return app


app = create_app()