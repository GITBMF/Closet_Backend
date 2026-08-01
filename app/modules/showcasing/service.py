from typing import List, Optional
from uuid import UUID

from app.modules.showcasing.repository import ShowcasingRepository
from app.modules.showcasing.schemas import (
    SponsorResponse, 
    SponsorCreate, 
    SponsorUpdate,
    FeaturedSlotResponse, 
    FeaturedSlotCreate, 
    FeaturedSlotUpdate,
    HomeShowcaseResponse
)
from app.modules.showcasing.exceptions import SponsorNotFoundException, FeaturedSlotNotFoundException
from app.modules.catalogue.exceptions import PieceNotFoundException
from app.modules.catalogue.repository import CatalogueRepository


class ShowcasingService:
    def __init__(self, repo: ShowcasingRepository, catalogue_repo: Optional[CatalogueRepository] = None):
        self.repo = repo
        self.catalogue_repo = catalogue_repo

    # --- Public Services ---
    async def get_home_showcase_data(self) -> HomeShowcaseResponse:
        sponsors = await self.repo.get_active_sponsors()
        featured = await self.repo.get_active_featured_slots()
        return HomeShowcaseResponse(sponsors=sponsors, featured_slots=featured)

    async def get_featured_by_type(self, slot_type: Optional[str] = None) -> List[FeaturedSlotResponse]:
        return await self.repo.get_active_featured_slots(slot_type=slot_type)

    # --- Admin Sponsor Services ---
    async def create_sponsor(self, payload: SponsorCreate) -> SponsorResponse:
        return await self.repo.create_sponsor(payload.model_dump())

    async def list_all_sponsors(self) -> List[SponsorResponse]:
        return await self.repo.get_all_sponsors()

    async def update_sponsor(self, sponsor_id: UUID, payload: SponsorUpdate) -> SponsorResponse:
        sponsor = await self.repo.get_sponsor_by_id(sponsor_id)
        if not sponsor:
            raise SponsorNotFoundException(str(sponsor_id))
        return await self.repo.update_sponsor(sponsor, payload.model_dump(exclude_unset=True))

    async def delete_sponsor(self, sponsor_id: UUID) -> bool:
        sponsor = await self.repo.get_sponsor_by_id(sponsor_id)
        if not sponsor:
            raise SponsorNotFoundException(str(sponsor_id))
        return await self.repo.delete_sponsor(sponsor)

    # --- Admin Featured Slot Services ---
    async def create_featured_slot(self, payload: FeaturedSlotCreate, user_id: Optional[UUID]) -> FeaturedSlotResponse:
        # Vérification de l'existence de la pièce dans le catalogue (Reads Catalogue)
        if self.catalogue_repo:
            piece = await self.catalogue_repo.get_piece_by_id(payload.piece_id)
            if not piece:
                raise PieceNotFoundException(str(payload.piece_id))

        return await self.repo.create_featured_slot(payload.model_dump(), user_id=user_id)

    async def list_all_featured_slots(self) -> List[FeaturedSlotResponse]:
        return await self.repo.get_all_featured_slots()

    async def update_featured_slot(self, slot_id: int, payload: FeaturedSlotUpdate) -> FeaturedSlotResponse:
        slot = await self.repo.get_featured_slot_by_id(slot_id)
        if not slot:
            raise FeaturedSlotNotFoundException(slot_id)
        return await self.repo.update_featured_slot(slot, payload.model_dump(exclude_unset=True))

    async def delete_featured_slot(self, slot_id: int) -> bool:
        slot = await self.repo.get_featured_slot_by_id(slot_id)
        if not slot:
            raise FeaturedSlotNotFoundException(slot_id)
        return await self.repo.delete_featured_slot(slot)