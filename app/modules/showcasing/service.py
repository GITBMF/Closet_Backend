"""Showcasing service — sponsors + featured slots over the catalogue.

Architecture rules honoured:
  * Cross-module reads go through the catalogue SERVICE, never its repository
    or tables. Featured slots are resolved to pieces via catalogue.browse-style
    reads (get_piece_for_order is the existing single-piece read contract).
  * This service owns the transaction; the repository only flushes.
  * A featured slot may only point at a piece that actually exists (validated
    through the catalogue service before insert).
"""

from __future__ import annotations

import uuid

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.catalogue.service import CatalogueService
from app.modules.showcasing.constants import FeaturedSlotType
from app.modules.showcasing.models import FeaturedSlot, Sponsor
from app.modules.showcasing.repository import ShowcasingRepository
from app.modules.showcasing.schemas import (
    FeaturedSlotCreate,
    FeaturedSlotUpdate,
    SponsorCreate,
    SponsorUpdate,
)


class ShowcasingService:
    def __init__(
        self, repo: ShowcasingRepository, catalogue: CatalogueService
    ) -> None:
        self.repo = repo
        self.catalogue = catalogue

    @property
    def db(self):
        return self.repo.db

    # =============================================================== public
    async def home(self) -> tuple[list[Sponsor], list[tuple[FeaturedSlot, object]]]:
        """Everything the storefront home needs: active sponsors + active
        featured slots resolved to their (published) pieces."""
        sponsors = await self.repo.active_sponsors()
        slots = await self.repo.active_featured()
        featured = await self._resolve_published(slots)
        return sponsors, featured

    async def active_sponsors(self) -> list[Sponsor]:
        return await self.repo.active_sponsors()

    async def active_featured(
        self, slot: FeaturedSlotType | None = None
    ) -> list[tuple[FeaturedSlot, object]]:
        slots = await self.repo.active_featured(slot)
        return await self._resolve_published(slots)

    async def _resolve_published(
        self, slots: list[FeaturedSlot]
    ) -> list[tuple[FeaturedSlot, object]]:
        """Attach each slot's piece via the catalogue service; drop slots whose
        piece is missing or not published (never surface a hidden piece)."""
        out: list[tuple[FeaturedSlot, object]] = []
        for slot in slots:
            piece = await self.catalogue.get_piece_for_order(slot.piece_id)
            if piece is None:
                continue
            status = getattr(piece, "status", None)
            if status is not None and getattr(status, "value", status) != "published":
                continue
            out.append((slot, piece))
        return out

    # ====================================================== admin: sponsors
    async def list_sponsors(self) -> list[Sponsor]:
        return await self.repo.all_sponsors()

    async def create_sponsor(self, payload: SponsorCreate) -> Sponsor:
        self._check_window(payload.starts_at, payload.ends_at)
        sponsor = Sponsor(**payload.model_dump())
        await self.repo.add_sponsor(sponsor)
        await self.db.commit()
        return await self.repo.get_sponsor(sponsor.id)

    async def update_sponsor(
        self, sponsor_id: uuid.UUID, payload: SponsorUpdate
    ) -> Sponsor:
        sponsor = await self.repo.get_sponsor(sponsor_id)
        if sponsor is None:
            raise NotFoundError("Sponsor introuvable.", code="sponsor_not_found")
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(sponsor, field, value)
        self._check_window(sponsor.starts_at, sponsor.ends_at)
        await self.db.commit()
        return await self.repo.get_sponsor(sponsor_id)

    async def delete_sponsor(self, sponsor_id: uuid.UUID) -> None:
        sponsor = await self.repo.get_sponsor(sponsor_id)
        if sponsor is None:
            raise NotFoundError("Sponsor introuvable.", code="sponsor_not_found")
        await self.repo.delete_sponsor(sponsor)
        await self.db.commit()

    # ================================================ admin: featured slots
    async def list_featured(self) -> list[tuple[FeaturedSlot, object]]:
        slots = await self.repo.all_featured()
        out = []
        for slot in slots:
            piece = await self.catalogue.get_piece_for_order(slot.piece_id)
            out.append((slot, piece))
        return out

    async def create_featured(
        self, payload: FeaturedSlotCreate, *, created_by: uuid.UUID | None
    ) -> FeaturedSlot:
        self._check_window(payload.starts_at, payload.ends_at)
        # the piece must exist (read via the catalogue service, not its repo)
        piece = await self.catalogue.get_piece_for_order(payload.piece_id)
        if piece is None:
            raise NotFoundError(
                "La pièce à mettre en avant est introuvable.", code="piece_not_found"
            )
        slot = FeaturedSlot(
            slot=payload.slot,
            piece_id=payload.piece_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            created_by=created_by,
        )
        await self.repo.add_featured(slot)
        await self.db.commit()
        return await self.repo.get_featured(slot.id)

    async def update_featured(
        self, slot_id: int, payload: FeaturedSlotUpdate
    ) -> FeaturedSlot:
        slot = await self.repo.get_featured(slot_id)
        if slot is None:
            raise NotFoundError("Slot introuvable.", code="featured_slot_not_found")
        data = payload.model_dump(exclude_unset=True)
        if "piece_id" in data:
            piece = await self.catalogue.get_piece_for_order(data["piece_id"])
            if piece is None:
                raise NotFoundError(
                    "La pièce est introuvable.", code="piece_not_found"
                )
        for field, value in data.items():
            setattr(slot, field, value)
        self._check_window(slot.starts_at, slot.ends_at)
        await self.db.commit()
        return await self.repo.get_featured(slot_id)

    async def delete_featured(self, slot_id: int) -> None:
        slot = await self.repo.get_featured(slot_id)
        if slot is None:
            raise NotFoundError("Slot introuvable.", code="featured_slot_not_found")
        await self.repo.delete_featured(slot)
        await self.db.commit()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _check_window(starts_at, ends_at) -> None:
        if starts_at is not None and ends_at is not None and ends_at < starts_at:
            raise ValidationError(
                "La date de fin doit être postérieure à la date de début.",
                code="invalid_window",
            )