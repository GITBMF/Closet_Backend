"""Seed Cameroon's geographic reference data on startup (when enabled).

`ensure_geo_seeded()` is called from the app lifespan. It is a no-op unless
``settings.SEED_GEO_ON_STARTUP`` is true, so the operator decides per
deployment whether the database should be populated.

The work itself (`_seed`) is fully idempotent: every row is inserted only if a
row with the same natural key is absent, so running it on every startup — or
after extending ``seed_data.py`` — never duplicates and only fills gaps. Tables
are assumed to exist already (created by the Alembic migrations); this only
inserts rows.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.geo.models import (
    Division,
    FixedRateCity,
    Neighbourhood,
    Region,
    Subdivision,
)
from app.modules.geo.seed_data import CITIES, REGIONS

logger = logging.getLogger("closet.geo.seed")


async def ensure_geo_seeded() -> None:
    """Populate the geo reference tables if SEED_GEO_ON_STARTUP is enabled."""
    if not getattr(settings, "SEED_GEO_ON_STARTUP", False):
        return
    try:
        async with AsyncSessionLocal() as session:
            inserted = await _seed(session)
            await session.commit()
    except Exception:  # never let seeding crash startup
        logger.exception("geo seed: failed; skipping")
        return
    if inserted:
        logger.info("geo seed: inserted %d new row(s)", inserted)
    else:
        logger.info("geo seed: nothing to insert (already present)")


async def _seed(session: AsyncSession) -> int:
    """Insert any missing geo rows. Returns the number of rows created."""
    created = 0
    region_by_code: dict[str, Region] = {}

    # --- administrative hierarchy: regions -> divisions -> subdivisions ------
    for r in REGIONS:
        region = (
            await session.execute(select(Region).where(Region.code == r["code"]))
        ).scalar_one_or_none()
        if region is None:
            region = Region(code=r["code"], name=r["name"])
            session.add(region)
            await session.flush()
            created += 1
        region_by_code[r["code"]] = region

        for d in r.get("divisions", []):
            division = (
                await session.execute(
                    select(Division).where(
                        Division.region_id == region.id, Division.name == d["name"]
                    )
                )
            ).scalar_one_or_none()
            if division is None:
                division = Division(region_id=region.id, name=d["name"])
                session.add(division)
                await session.flush()
                created += 1

            for sub_name in d.get("subdivisions", []):
                exists = (
                    await session.execute(
                        select(Subdivision.id).where(
                            Subdivision.division_id == division.id,
                            Subdivision.name == sub_name,
                        )
                    )
                ).scalar_one_or_none()
                if exists is None:
                    session.add(Subdivision(division_id=division.id, name=sub_name))
                    created += 1

    # --- delivery zones: fixed-rate cities -> neighbourhoods -----------------
    for c in CITIES:
        region = region_by_code.get(c["region"])
        if region is None:
            region = (
                await session.execute(
                    select(Region).where(Region.code == c["region"])
                )
            ).scalar_one_or_none()
        if region is None:
            logger.warning(
                "geo seed: city %r references unknown region %r — skipped",
                c["name"], c["region"],
            )
            continue

        city = (
            await session.execute(
                select(FixedRateCity).where(FixedRateCity.name == c["name"])
            )
        ).scalar_one_or_none()
        if city is None:
            city = FixedRateCity(
                name=c["name"], region_id=region.id, is_active=c.get("is_active", True)
            )
            session.add(city)
            await session.flush()
            created += 1

        for n in c.get("neighbourhoods", []):
            exists = (
                await session.execute(
                    select(Neighbourhood.id).where(
                        Neighbourhood.city_id == city.id, Neighbourhood.name == n
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(Neighbourhood(city_id=city.id, name=n))
                created += 1

    return created
