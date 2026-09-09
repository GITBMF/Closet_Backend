"""Manually seed Cameroon's geo reference data into an existing database.

    python -m scripts.seed_geo

Runs the same idempotent seeding as startup, but unconditionally (it ignores
the SEED_GEO_ON_STARTUP flag), so you can populate a database on demand — handy
for the deployed instance where you left the startup flag off.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.database import AsyncSessionLocal, engine
from app.modules.geo.seed import _seed


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    async with AsyncSessionLocal() as session:
        created = await _seed(session)
        await session.commit()
    print(f"geo seed: inserted {created} new row(s)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
