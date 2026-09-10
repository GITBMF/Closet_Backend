"""Geographic reference models — the delivery-zone hierarchy.

region -> division -> subdivision  (administrative hierarchy, for addresses)
region -> fixed_rate_city -> neighbourhood  (the delivery-pricing hierarchy)

These are small, mostly-static reference tables. Integer PKs (smallint/int)
are deliberate: there are a bounded, small number of rows and they are
referenced heavily by other modules, so narrow keys keep those FKs cheap.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Region(Base):
    """Top-level administrative region (e.g. Centre, Littoral)."""

    __tablename__ = "region"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)

    divisions: Mapped[list[Division]] = relationship(
        back_populates="region", cascade="all, delete-orphan"
    )

    async def __admin_repr__(self, request) -> str:  # noqa: ANN001
        return self.name


class Division(Base):
    """Second-level division within a region."""

    __tablename__ = "division"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("region.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    region: Mapped[Region] = relationship(back_populates="divisions")
    subdivisions: Mapped[list[Subdivision]] = relationship(
        back_populates="division", cascade="all, delete-orphan"
    )


class Subdivision(Base):
    """Third-level subdivision within a division."""

    __tablename__ = "subdivision"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    division_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("division.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    division: Mapped[Division] = relationship(back_populates="subdivisions")


class FixedRateCity(Base):
    """A city that has a flat delivery rate (the delivery-pricing zone).

    Distinct from the administrative hierarchy: delivery fees are quoted per
    fixed-rate city (or per region for out-of-zone destinations).
    """

    __tablename__ = "fixed_rate_city"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    region_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("region.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    neighbourhoods: Mapped[list[Neighbourhood]] = relationship(
        back_populates="city", cascade="all, delete-orphan"
    )

    async def __admin_repr__(self, request) -> str:  # noqa: ANN001
        return self.name


class Neighbourhood(Base):
    """A neighbourhood within a fixed-rate city (delivery granularity)."""

    __tablename__ = "neighbourhood"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("fixed_rate_city.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    city: Mapped[FixedRateCity] = relationship(back_populates="neighbourhoods")