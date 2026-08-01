from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, status

from app.modules.showcasing.schemas import (
    SponsorResponse, 
    SponsorCreate, 
    SponsorUpdate,
    FeaturedSlotResponse, 
    FeaturedSlotCreate, 
    FeaturedSlotUpdate,
    HomeShowcaseResponse
)
from app.modules.showcasing.service import ShowcasingService
from app.modules.showcasing.dependencies import get_showcasing_service
from app.modules.identity.dependencies import get_current_user

# On crée le routeur principal pour le préfixe URL /showcasing
router = APIRouter(prefix="/showcasing")


# ==============================================================================
# 🌐 PARTIE PUBLIQUE : Tag "Showcasing & Sponsors"
# ==============================================================================

@router.get(
    "/home", 
    response_model=HomeShowcaseResponse, 
    tags=["Showcasing & Sponsors"],
    summary="Get Home Showcase"
)
async def get_home_showcase(service: ShowcasingService = Depends(get_showcasing_service)):
    return await service.get_home_showcase_data()


@router.get(
    "/sponsors", 
    response_model=List[SponsorResponse], 
    tags=["Showcasing & Sponsors"],
    summary="Get Active Sponsors"
)
async def get_active_sponsors(service: ShowcasingService = Depends(get_showcasing_service)):
    return await service.repo.get_active_sponsors()


@router.get(
    "/featured", 
    response_model=List[FeaturedSlotResponse], 
    tags=["Showcasing & Sponsors"],
    summary="Get Featured Slots"
)
async def get_featured_slots(
    slot_type: Optional[str] = None,
    service: ShowcasingService = Depends(get_showcasing_service)
):
    return await service.get_featured_by_type(slot_type)


# ==============================================================================
# 🔐 PARTIE ADMINISTRATION : Tag "ADMIN Showcasing & Sponsors"
# ==============================================================================

# --- Admin Sponsors ---

@router.get(
    "/admin/sponsors", 
    response_model=List[SponsorResponse], 
    tags=["ADMIN Showcasing & Sponsors"],
    summary="List All Sponsors"
)
async def list_all_sponsors(
    current_user = Depends(get_current_user),
    service: ShowcasingService = Depends(get_showcasing_service)
):
    return await service.list_all_sponsors()


@router.post(
    "/admin/sponsors", 
    response_model=SponsorResponse, 
    status_code=status.HTTP_201_CREATED, 
    tags=["ADMIN Showcasing & Sponsors"],
    summary="Create Sponsor"
)
async def create_sponsor(
    payload: SponsorCreate,
    current_user = Depends(get_current_user),
    service: ShowcasingService = Depends(get_showcasing_service)
):
    return await service.create_sponsor(payload)


@router.patch(
    "/admin/sponsors/{sponsor_id}", 
    response_model=SponsorResponse, 
    tags=["ADMIN Showcasing & Sponsors"],
    summary="Update Sponsor"
)
async def update_sponsor(
    sponsor_id: UUID,
    payload: SponsorUpdate,
    current_user = Depends(get_current_user),
    service: ShowcasingService = Depends(get_showcasing_service)
):
    return await service.update_sponsor(sponsor_id, payload)


@router.delete(
    "/admin/sponsors/{sponsor_id}", 
    status_code=status.HTTP_204_NO_CONTENT, 
    tags=["ADMIN Showcasing & Sponsors"],
    summary="Delete Sponsor"
)
async def delete_sponsor(
    sponsor_id: UUID,
    current_user = Depends(get_current_user),
    service: ShowcasingService = Depends(get_showcasing_service)
):
    await service.delete_sponsor(sponsor_id)


# --- Admin Featured Slots ---

@router.get(
    "/admin/featured", 
    response_model=List[FeaturedSlotResponse], 
    tags=["ADMIN Showcasing & Sponsors"],
    summary="List All Featured Slots"
)
async def list_all_featured_slots(
    current_user = Depends(get_current_user),
    service: ShowcasingService = Depends(get_showcasing_service)
):
    return await service.list_all_featured_slots()


@router.post(
    "/admin/featured", 
    response_model=FeaturedSlotResponse, 
    status_code=status.HTTP_201_CREATED, 
    tags=["ADMIN Showcasing & Sponsors"],
    summary="Create Featured Slot"
)
async def create_featured_slot(
    payload: FeaturedSlotCreate,
    current_user = Depends(get_current_user),
    service: ShowcasingService = Depends(get_showcasing_service)
):
    return await service.create_featured_slot(payload, user_id=current_user.id)


@router.patch(
    "/admin/featured/{slot_id}", 
    response_model=FeaturedSlotResponse, 
    tags=["ADMIN Showcasing & Sponsors"],
    summary="Update Featured Slot"
)
async def update_featured_slot(
    slot_id: int,
    payload: FeaturedSlotUpdate,
    current_user = Depends(get_current_user),
    service: ShowcasingService = Depends(get_showcasing_service)
):
    return await service.update_featured_slot(slot_id, payload)


@router.delete(
    "/admin/featured/{slot_id}", 
    status_code=status.HTTP_204_NO_CONTENT, 
    tags=["ADMIN Showcasing & Sponsors"],
    summary="Delete Featured Slot"
)
async def delete_featured_slot(
    slot_id: int,
    current_user = Depends(get_current_user),
    service: ShowcasingService = Depends(get_showcasing_service)
):
    await service.delete_featured_slot(slot_id)