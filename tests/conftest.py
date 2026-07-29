"""Shared test fixtures.

The schema is built once per session here so every test module shares it
(each module defining its own DROP SCHEMA fixture would fight the others).
Per-module fixtures handle their own seeding and cleanup.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text

from app.core.database import engine
from app.db.registry import Base


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        # Extensions the models rely on (citext, pgcrypto); the migration
        # enables these too.
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "citext"'))
        # Every PG enum is declared create_type=False (the migration owns them);
        # build them from the metadata so this never drifts from the models.
        seen: set[str] = set()
        for table in Base.metadata.tables.values():
            for column in table.columns:
                if getattr(column.type, "native_enum", None):
                    name = getattr(column.type, "name", None)
                    if name and name not in seen:
                        seen.add(name)
                        await conn.run_sync(column.type.create, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()