"""Catalogue repository — all catalogue SQL.

Browse is filtered and paginated; search uses the piece.search_vector
(a Postgres tsvector kept in step by a trigger the migration installs, or
recomputed on write here). Reservation methods are used by the orders module
through the service, never directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.catalogue.constants import PieceStatus
from app.modules.catalogue.models import (
    House,
    Piece,
    PieceMedia,
    PublicationBatch,
    Universe,
    WishlistItem,
)


class CatalogueRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------- houses / universes
    async def list_houses(self, *, active_only: bool = True) -> list[House]:
        stmt = select(House).order_by(House.name)
        if active_only:
            stmt = stmt.where(House.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_house(self, house_id: uuid.UUID) -> House | None:
        return await self.db.get(House, house_id)

    async def add_house(self, house: House) -> House:
        self.db.add(house)
        await self.db.flush()
        return house

    async def list_universes(self, *, active_only: bool = True) -> list[Universe]:
        stmt = select(Universe).order_by(Universe.position, Universe.name)
        if active_only:
            stmt = stmt.where(Universe.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_universe(self, universe_id: uuid.UUID) -> Universe | None:
        return await self.db.get(Universe, universe_id)

    async def add_universe(self, universe: Universe) -> Universe:
        self.db.add(universe)
        await self.db.flush()
        return universe

    # ------------------------------------------------------------- pieces
    async def get_piece(
        self, piece_id: uuid.UUID, *, with_media: bool = False
    ) -> Piece | None:
        stmt = select(Piece).where(Piece.id == piece_id, Piece.deleted_at.is_(None))
        if with_media:
            stmt = stmt.options(selectinload(Piece.media))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_piece_by_slug(
        self, slug: str, *, with_media: bool = False
    ) -> Piece | None:
        stmt = select(Piece).where(Piece.slug == slug, Piece.deleted_at.is_(None))
        if with_media:
            stmt = stmt.options(selectinload(Piece.media))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def sku_exists(self, sku: str) -> bool:
        stmt = select(func.count()).select_from(Piece).where(Piece.sku == sku)
        return bool((await self.db.execute(stmt)).scalar_one())

    async def slug_exists(self, slug: str) -> bool:
        stmt = select(func.count()).select_from(Piece).where(Piece.slug == slug)
        return bool((await self.db.execute(stmt)).scalar_one())

    def _browse_stmt(
        self,
        *,
        status: PieceStatus | None,
        house_id: uuid.UUID | None,
        universe_id: uuid.UUID | None,
        min_price=None,
        max_price=None,
        search: str | None,
    ):
        stmt = select(Piece).where(Piece.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(Piece.status == status)
        if house_id is not None:
            stmt = stmt.where(Piece.house_id == house_id)
        if universe_id is not None:
            stmt = stmt.where(Piece.universe_id == universe_id)
        if min_price is not None:
            stmt = stmt.where(Piece.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(Piece.price <= max_price)
        if search:
            # full-text when the vector is populated, else a simple ILIKE
            ts = func.plainto_tsquery("simple", search)
            stmt = stmt.where(
                or_(
                    Piece.search_vector.op("@@")(ts),
                    Piece.title.ilike(f"%{search}%"),
                )
            )
        return stmt

    async def browse(
        self,
        *,
        status: PieceStatus | None = PieceStatus.PUBLISHED,
        house_id: uuid.UUID | None = None,
        universe_id: uuid.UUID | None = None,
        min_price=None,
        max_price=None,
        search: str | None = None,
        limit: int = 24,
        offset: int = 0,
    ) -> tuple[list[Piece], int]:
        base = self._browse_stmt(
            status=status, house_id=house_id, universe_id=universe_id,
            min_price=min_price, max_price=max_price, search=search,
        )
        total = (
            await self.db.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(Piece.published_at.desc().nullslast(), Piece.title)
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def add_piece(self, piece: Piece) -> Piece:
        self.db.add(piece)
        await self.db.flush()
        return piece

    async def recompute_search_vector(self, piece_id: uuid.UUID) -> None:
        """Rebuild the tsvector for one piece from its text fields."""
        await self.db.execute(
            Piece.__table__.update()
            .where(Piece.id == piece_id)
            .values(
                search_vector=func.to_tsvector(
                    "simple",
                    func.coalesce(Piece.title, "")
                    + " "
                    + func.coalesce(Piece.description, "")
                    + " "
                    + func.coalesce(Piece.size_label, ""),
                )
            )
        )

    # --------------------------------------------------------------- media
    async def get_media(self, media_id: uuid.UUID) -> PieceMedia | None:
        return await self.db.get(PieceMedia, media_id)

    async def add_media(self, media: PieceMedia) -> PieceMedia:
        self.db.add(media)
        await self.db.flush()
        return media

    async def delete_media(self, media: PieceMedia) -> None:
        await self.db.delete(media)
        await self.db.flush()

    # -------------------------------------------------- publication batches
    async def add_batch(self, batch: PublicationBatch) -> PublicationBatch:
        self.db.add(batch)
        await self.db.flush()
        return batch

    async def list_batches(self) -> list[PublicationBatch]:
        stmt = select(PublicationBatch).order_by(PublicationBatch.created_at.desc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def pieces_by_ids(self, piece_ids: list[uuid.UUID]) -> list[Piece]:
        stmt = select(Piece).where(
            Piece.id.in_(piece_ids), Piece.deleted_at.is_(None)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # ------------------------------------------------------------ wishlist
    async def wishlist_piece_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        stmt = select(WishlistItem.piece_id).where(WishlistItem.user_id == user_id)
        return set((await self.db.execute(stmt)).scalars().all())

    async def is_in_wishlist(self, user_id: uuid.UUID, piece_id: uuid.UUID) -> bool:
        return (
            await self.db.get(WishlistItem, {"user_id": user_id, "piece_id": piece_id})
        ) is not None

    async def wishlist_pieces(self, user_id: uuid.UUID) -> list[Piece]:
        stmt = (
            select(Piece)
            .join(WishlistItem, WishlistItem.piece_id == Piece.id)
            .where(WishlistItem.user_id == user_id, Piece.deleted_at.is_(None))
            .order_by(WishlistItem.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def add_wishlist(self, user_id: uuid.UUID, piece_id: uuid.UUID) -> None:
        self.db.add(WishlistItem(user_id=user_id, piece_id=piece_id))
        await self.db.flush()

    async def remove_wishlist(self, user_id: uuid.UUID, piece_id: uuid.UUID) -> None:
        item = await self.db.get(
            WishlistItem, {"user_id": user_id, "piece_id": piece_id}
        )
        if item is not None:
            await self.db.delete(item)
            await self.db.flush()

    # ---------------------------------------- reservation (called by orders)
    async def reserve(
        self, piece_id: uuid.UUID, *, order_id: uuid.UUID, until: datetime
    ) -> bool:
        """Atomically move a published piece to reserved. Returns False if it
        wasn't available (already sold/reserved by someone else)."""
        result = await self.db.execute(
            Piece.__table__.update()
            .where(
                Piece.id == piece_id,
                Piece.status == PieceStatus.PUBLISHED,
                Piece.deleted_at.is_(None),
            )
            .values(
                status=PieceStatus.RESERVED,
                reserved_by_order_id=order_id,
                reserved_until=until,
            )
        )
        return result.rowcount == 1

    async def release(self, piece_id: uuid.UUID) -> None:
        """Return a reserved piece to published (reservation expired/cancelled)."""
        await self.db.execute(
            Piece.__table__.update()
            .where(Piece.id == piece_id, Piece.status == PieceStatus.RESERVED)
            .values(
                status=PieceStatus.PUBLISHED,
                reserved_by_order_id=None,
                reserved_until=None,
            )
        )

    async def mark_sold(self, piece_id: uuid.UUID) -> None:
        await self.db.execute(
            Piece.__table__.update()
            .where(Piece.id == piece_id)
            .values(status=PieceStatus.SOLD)
        )