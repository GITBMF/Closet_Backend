"""Catalogue service — piece lifecycle, browse/search, and the cross-module
hooks orders and sourcing depend on.

Lifecycle:  draft --publish--> published --reserve--> reserved --sold--> sold
                                    ^------release------/

Cross-module contracts (call these, never the repo, from other modules):
  * reserve(piece_id, order_id, minutes)  -> orders, at checkout
  * release(piece_id)                      -> orders, on cancel/expiry
  * mark_sold(piece_id)                    -> orders, on payment success
  * create_from_submission(...)            -> sourcing, when cataloguing
"""

from __future__ import annotations

import contextlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.storage import StorageError, StorageProvider
from app.modules.catalogue.constants import MediaType, PieceStatus
from app.modules.catalogue.models import (
    House,
    Piece,
    PieceMedia,
    PublicationBatch,
    Universe,
)
from app.modules.catalogue.repository import CatalogueRepository
from app.modules.catalogue.schemas import (
    HouseCreate,
    MediaMeta,
    PieceCreate,
    PieceUpdate,
    PublicationBatchCreate,
    UniverseCreate,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-") or "item"


_EXT_BY_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class CatalogueService:
    def __init__(
        self, repo: CatalogueRepository, storage: StorageProvider | None = None
    ) -> None:
        self.repo = repo
        self._storage = storage

    # ---------------------------------------------------- houses / universes
    async def list_houses(self, *, active_only: bool = True) -> list[House]:
        return await self.repo.list_houses(active_only=active_only)

    async def create_house(self, payload: HouseCreate) -> House:
        slug = payload.slug or _slugify(payload.name)
        house = House(name=payload.name.strip(), slug=slug, is_active=payload.is_active)
        house = await self.repo.add_house(house)
        await self.repo.db.commit()
        await self.repo.db.refresh(house)
        return house

    async def list_universes(self, *, active_only: bool = True) -> list[Universe]:
        return await self.repo.list_universes(active_only=active_only)

    async def create_universe(self, payload: UniverseCreate) -> Universe:
        slug = payload.slug or _slugify(payload.name)
        universe = Universe(
            name=payload.name.strip(), slug=slug,
            position=payload.position, is_active=payload.is_active,
        )
        universe = await self.repo.add_universe(universe)
        await self.repo.db.commit()
        await self.repo.db.refresh(universe)
        return universe

    # ------------------------------------------------------------- browse
    async def browse(self, **kwargs) -> tuple[list[Piece], int]:
        return await self.repo.browse(**kwargs)

    async def get_detail(
        self, piece_id: uuid.UUID, *, viewer_id: uuid.UUID | None = None
    ) -> tuple[Piece, bool]:
        piece = await self.repo.get_piece(piece_id, with_media=True)
        if piece is None:
            raise NotFoundError("Article introuvable.", code="piece_not_found")
        in_wishlist = False
        if viewer_id is not None:
            in_wishlist = await self.repo.is_in_wishlist(viewer_id, piece_id)
        return piece, in_wishlist

    # ------------------------------------------------- piece write lifecycle
    async def _unique_sku(self, proposed: str | None) -> str:
        if proposed:
            if await self.repo.sku_exists(proposed):
                raise ConflictError("SKU déjà utilisé.", code="sku_taken")
            return proposed
        # generate CLO-XXXXXX until free
        for _ in range(10):
            candidate = f"CLO-{secrets.token_hex(3).upper()}"
            if not await self.repo.sku_exists(candidate):
                return candidate
        raise ConflictError("Impossible de générer un SKU.", code="sku_generation_failed")

    async def _unique_slug(self, title: str, proposed: str | None) -> str:
        base = proposed or _slugify(title)
        if not await self.repo.slug_exists(base):
            return base
        for _ in range(50):
            candidate = f"{base}-{secrets.token_hex(2)}"
            if not await self.repo.slug_exists(candidate):
                return candidate
        raise ConflictError("Impossible de générer un slug.", code="slug_generation_failed")

    async def create_piece(self, payload: PieceCreate) -> Piece:
        # validate referenced house/universe exist
        if payload.house_id and await self.repo.get_house(payload.house_id) is None:
            raise NotFoundError("Maison introuvable.", code="house_not_found")
        if payload.universe_id and await self.repo.get_universe(payload.universe_id) is None:
            raise NotFoundError("Univers introuvable.", code="universe_not_found")

        piece = Piece(
            sku=await self._unique_sku(payload.sku),
            title=payload.title.strip(),
            slug=await self._unique_slug(payload.title, payload.slug),
            description=payload.description,
            story=payload.story,
            house_id=payload.house_id,
            universe_id=payload.universe_id,
            size_label=payload.size_label,
            condition=payload.condition,
            price=payload.price,
            currency=payload.currency,
            status=PieceStatus.DRAFT,
            sourcer_id=payload.sourcer_id,
            acquisition_type=payload.acquisition_type,
            acquisition_cost=payload.acquisition_cost,
            consignment_share_percent=payload.consignment_share_percent,
        )
        piece = await self.repo.add_piece(piece)
        await self.repo.recompute_search_vector(piece.id)
        await self.repo.db.commit()
        await self.repo.db.refresh(piece)
        return piece

    async def update_piece(self, piece_id: uuid.UUID, payload: PieceUpdate) -> Piece:
        piece = await self.repo.get_piece(piece_id)
        if piece is None:
            raise NotFoundError("Article introuvable.", code="piece_not_found")
        data = payload.model_dump(exclude_unset=True)
        if data.get("house_id") is not None and (
            await self.repo.get_house(data["house_id"]) is None
        ):
            raise NotFoundError("Maison introuvable.", code="house_not_found")
        if data.get("universe_id") is not None and (
            await self.repo.get_universe(data["universe_id"]) is None
        ):
            raise NotFoundError("Univers introuvable.", code="universe_not_found")
        for field, value in data.items():
            setattr(piece, field, value.strip() if field == "title" else value)
        await self.repo.recompute_search_vector(piece.id)
        await self.repo.db.commit()
        await self.repo.db.refresh(piece)
        return piece

    async def delete_piece(self, piece_id: uuid.UUID) -> None:
        piece = await self.repo.get_piece(piece_id)
        if piece is None:
            raise NotFoundError("Article introuvable.", code="piece_not_found")
        if piece.status == PieceStatus.SOLD:
            raise ConflictError(
                "Un article vendu ne peut pas être supprimé.", code="piece_sold"
            )
        piece.deleted_at = datetime.now(UTC)
        await self.repo.db.commit()

    async def publish_piece(self, piece_id: uuid.UUID) -> Piece:
        piece = await self.repo.get_piece(piece_id)
        if piece is None:
            raise NotFoundError("Article introuvable.", code="piece_not_found")
        if piece.status not in (PieceStatus.DRAFT, PieceStatus.WITHDRAWN):
            raise ConflictError(
                "Seul un brouillon peut être publié.", code="not_publishable"
            )
        piece.status = PieceStatus.PUBLISHED
        piece.published_at = datetime.now(UTC)
        await self.repo.db.commit()
        await self.repo.db.refresh(piece)
        return piece

    # --------------------------------------------------------------- media
    def _storage_key_from_url(self, url: str) -> str | None:
        """Recover the object key from a stored URL (for deletion)."""
        base = settings.S3_PUBLIC_BASE_URL.rstrip("/") + "/"
        if url.startswith(base):
            return url[len(base):]
        return None

    async def add_media(
        self,
        piece_id: uuid.UUID,
        *,
        data: bytes,
        content_type: str,
        meta: MediaMeta,
    ) -> PieceMedia:
        if await self.repo.get_piece(piece_id) is None:
            raise NotFoundError("Article introuvable.", code="piece_not_found")

        # validate the upload
        if content_type not in settings.MEDIA_ALLOWED_TYPES:
            raise ValidationError(
                f"Type de fichier non supporté: {content_type}.",
                code="unsupported_media_type",
            )
        if len(data) == 0:
            raise ValidationError("Fichier vide.", code="empty_file")
        if len(data) > settings.MEDIA_MAX_BYTES:
            raise ValidationError(
                "Fichier trop volumineux.", code="file_too_large"
            )
        if self._storage is None:
            raise ValidationError(
                "Stockage indisponible.", code="storage_unavailable"
            )

        # upload to object storage, backend-generated key + url
        ext = _EXT_BY_TYPE.get(content_type, "bin")
        key = f"pieces/{piece_id}/{uuid.uuid4().hex}.{ext}"
        try:
            stored = await self._storage.put(
                key=key, data=data, content_type=content_type
            )
        except StorageError as exc:
            raise ValidationError(
                "Échec du téléversement.", code="upload_failed"
            ) from exc

        media = PieceMedia(
            piece_id=piece_id,
            url=stored.url,
            media_type=MediaType.IMAGE,
            view_label=meta.view_label,
            position=meta.position,
        )
        media = await self.repo.add_media(media)
        await self.repo.db.commit()
        await self.repo.db.refresh(media)
        return media

    async def remove_media(self, piece_id: uuid.UUID, media_id: uuid.UUID) -> None:
        media = await self.repo.get_media(media_id)
        if media is None or media.piece_id != piece_id:
            raise NotFoundError("Média introuvable.", code="media_not_found")
        # best-effort delete of the stored object, then the row
        key = self._storage_key_from_url(media.url)
        if key and self._storage is not None:
            # best-effort: don't block row removal on a storage hiccup
            with contextlib.suppress(StorageError):
                await self._storage.delete(key=key)
        await self.repo.delete_media(media)
        await self.repo.db.commit()

    # -------------------------------------------------- publication batches
    async def create_batch(
        self, payload: PublicationBatchCreate, *, published_by: uuid.UUID | None
    ) -> PublicationBatch:
        pieces = await self.repo.pieces_by_ids(payload.piece_ids)
        found = {p.id for p in pieces}
        missing = set(payload.piece_ids) - found
        if missing:
            raise NotFoundError(
                f"{len(missing)} article(s) introuvable(s).", code="pieces_not_found"
            )
        now = datetime.now(UTC)
        batch = PublicationBatch(
            label=payload.label, published_at=now, published_by=published_by
        )
        batch = await self.repo.add_batch(batch)
        # publish every piece in the batch
        for piece in pieces:
            piece.publication_batch_id = batch.id
            if piece.status in (PieceStatus.DRAFT, PieceStatus.WITHDRAWN):
                piece.status = PieceStatus.PUBLISHED
                piece.published_at = now
        await self.repo.db.commit()
        await self.repo.db.refresh(batch)
        return batch

    async def list_batches(self) -> list[PublicationBatch]:
        return await self.repo.list_batches()

    # ------------------------------------------------------------ wishlist
    async def list_wishlist(self, user_id: uuid.UUID) -> list[Piece]:
        return await self.repo.wishlist_pieces(user_id)

    async def add_to_wishlist(self, user_id: uuid.UUID, piece_id: uuid.UUID) -> None:
        if await self.repo.get_piece(piece_id) is None:
            raise NotFoundError("Article introuvable.", code="piece_not_found")
        if not await self.repo.is_in_wishlist(user_id, piece_id):
            await self.repo.add_wishlist(user_id, piece_id)
            await self.repo.db.commit()

    async def remove_from_wishlist(self, user_id: uuid.UUID, piece_id: uuid.UUID) -> None:
        await self.repo.remove_wishlist(user_id, piece_id)
        await self.repo.db.commit()

    async def get_piece_for_order(self, piece_id: uuid.UUID):
        """Read a piece for order snapshotting (title/price/status/currency).

        Returns the Piece or None. Called by the orders module — a plain read
        that does not commit.
        """
        return await self.repo.get_piece(piece_id)

    # =======================================================================
    # Cross-module contracts — called by OTHER modules through this service.
    # =======================================================================
    async def reserve(
        self, piece_id: uuid.UUID, *, order_id: uuid.UUID, minutes: int = 15
    ) -> bool:
        """Hold a published piece for an order. False if unavailable.

        Caller (orders) owns the commit — this participates in the order's
        transaction so reserving N pieces is atomic with creating the order.
        """
        until = datetime.now(UTC) + timedelta(minutes=minutes)
        return await self.repo.reserve(piece_id, order_id=order_id, until=until)

    async def release(self, piece_id: uuid.UUID) -> None:
        """Return a reserved piece to published (order cancelled/expired)."""
        await self.repo.release(piece_id)

    async def mark_sold(self, piece_id: uuid.UUID) -> None:
        """Finalize a piece as sold (payment confirmed)."""
        await self.repo.mark_sold(piece_id)

    async def restock(self, piece_id: uuid.UUID) -> None:
        """Put a returned piece back on sale (SOLD -> published).

        Called by the returns module when an approved return is resolved and the
        item has been received back. Caller owns the commit.
        """
        await self.repo.restock(piece_id)

    async def create_from_submission(
        self,
        *,
        title: str,
        condition,
        price,
        sourcer_id: uuid.UUID,
        house_id: uuid.UUID | None = None,
        universe_id: uuid.UUID | None = None,
        size_label: str | None = None,
        story: str | None = None,
        acquisition_type=None,
    ) -> Piece:
        """Create a draft piece from an accepted sourcing submission.

        Called by the sourcing module. Returns the new piece so sourcing can
        link submission.piece_id. Caller owns the commit.
        """
        if not title:
            raise ValidationError("Titre requis.", code="title_required")
        piece = Piece(
            sku=await self._unique_sku(None),
            title=title.strip(),
            slug=await self._unique_slug(title, None),
            story=story,
            house_id=house_id,
            universe_id=universe_id,
            size_label=size_label,
            condition=condition,
            price=price,
            status=PieceStatus.DRAFT,
            sourcer_id=sourcer_id,
            acquisition_type=acquisition_type,
        )
        piece = await self.repo.add_piece(piece)
        await self.repo.recompute_search_vector(piece.id)
        return piece