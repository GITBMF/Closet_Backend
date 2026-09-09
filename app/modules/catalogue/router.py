"""Catalogue HTTP layer.

  * `router`       -> /pieces, /houses, /universes, /wishlist  (public + customer)
  * `admin_router` -> /admin/*  piece / media / batch / vocab management

Browse and detail are public (the storefront works pre-login). Wishlist needs
a logged-in customer. Detail accepts an optional user so it can flag
in_wishlist without requiring auth.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.modules.catalogue.constants import PieceStatus
from app.modules.catalogue.dependencies import Service
from app.modules.catalogue.schemas import (
    HouseCreate,
    HouseOut,
    MediaMeta,
    MediaOut,
    PieceCreate,
    PieceDetail,
    PiecesPage,
    PieceSummary,
    PieceUpdate,
    PublicationBatchCreate,
    PublicationBatchOut,
    UniverseCreate,
    UniverseOut,
)
from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import (
    CurrentUser,
    OptionalUser,
    Shopper,
    require_permission,
)

router = APIRouter(tags=["catalogue"])
admin_router = APIRouter(prefix="/admin", tags=["admin: catalogue"])


# =========================================================== public browse
@router.get("/pieces", response_model=PiecesPage)
async def browse_pieces(
    service: Service,
    house_id: Annotated[uuid.UUID | None, Query()] = None,
    universe_id: Annotated[uuid.UUID | None, Query()] = None,
    min_price: Annotated[float | None, Query(ge=0)] = None,
    max_price: Annotated[float | None, Query(ge=0)] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PiecesPage:
    items, total = await service.browse(
        status=PieceStatus.PUBLISHED,
        house_id=house_id, universe_id=universe_id,
        min_price=min_price, max_price=max_price, search=q,
        limit=limit, offset=offset,
    )
    return PiecesPage(
        items=[PieceSummary.from_piece(p) for p in items],
        total=total, limit=limit, offset=offset,
    )


@router.get("/pieces/search", response_model=PiecesPage)
async def search_pieces(
    service: Service,
    q: Annotated[str, Query(min_length=1, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PiecesPage:
    items, total = await service.browse(
        status=PieceStatus.PUBLISHED, search=q, limit=limit, offset=offset
    )
    return PiecesPage(
        items=[PieceSummary.from_piece(p) for p in items],
        total=total, limit=limit, offset=offset,
    )


@router.get("/pieces/{piece_id}", response_model=PieceDetail)
async def get_piece(
    piece_id: uuid.UUID, service: Service, user: OptionalUser
) -> PieceDetail:
    piece, in_wishlist = await service.get_detail(
        piece_id, viewer_id=user.id if user else None
    )
    detail = PieceDetail.from_piece(piece)
    detail.in_wishlist = in_wishlist
    return detail


@router.get("/houses", response_model=list[HouseOut])
async def list_houses(service: Service) -> list[HouseOut]:
    return [HouseOut.model_validate(h) for h in await service.list_houses()]


@router.get("/universes", response_model=list[UniverseOut])
async def list_universes(service: Service) -> list[UniverseOut]:
    return [UniverseOut.model_validate(u) for u in await service.list_universes()]


# ============================================================ customer wishlist
@router.get("/wishlist", response_model=list[PieceSummary])
async def my_wishlist(service: Service, user: Shopper) -> list[PieceSummary]:
    return [PieceSummary.from_piece(p) for p in await service.list_wishlist(user.id)]


@router.post("/wishlist/{piece_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_to_wishlist(
    piece_id: uuid.UUID, service: Service, user: Shopper
) -> Response:
    await service.add_to_wishlist(user.id, piece_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/wishlist/{piece_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(
    piece_id: uuid.UUID, service: Service, user: Shopper
) -> Response:
    await service.remove_from_wishlist(user.id, piece_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ================================================================ admin: vocab
@admin_router.post(
    "/houses", response_model=HouseOut, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CATALOGUE_WRITE))],
)
async def create_house(payload: HouseCreate, service: Service) -> HouseOut:
    return HouseOut.model_validate(await service.create_house(payload))


@admin_router.post(
    "/universes", response_model=UniverseOut, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CATALOGUE_WRITE))],
)
async def create_universe(payload: UniverseCreate, service: Service) -> UniverseOut:
    return UniverseOut.model_validate(await service.create_universe(payload))


# ============================================================== admin: pieces
@admin_router.post(
    "/pieces", response_model=PieceDetail, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CATALOGUE_WRITE))],
)
async def create_piece(payload: PieceCreate, service: Service) -> PieceDetail:
    piece = await service.create_piece(payload)
    piece, _ = await service.get_detail(piece.id)
    return PieceDetail.from_piece(piece)


@admin_router.patch(
    "/pieces/{piece_id}", response_model=PieceDetail,
    dependencies=[Depends(require_permission(Permission.CATALOGUE_WRITE))],
)
async def update_piece(
    piece_id: uuid.UUID, payload: PieceUpdate, service: Service
) -> PieceDetail:
    await service.update_piece(piece_id, payload)
    piece, _ = await service.get_detail(piece_id)
    return PieceDetail.from_piece(piece)


@admin_router.delete(
    "/pieces/{piece_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permission.CATALOGUE_WRITE))],
)
async def delete_piece(piece_id: uuid.UUID, service: Service) -> Response:
    await service.delete_piece(piece_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/pieces/{piece_id}/publish", response_model=PieceDetail,
    dependencies=[Depends(require_permission(Permission.CATALOGUE_PUBLISH))],
)
async def publish_piece(piece_id: uuid.UUID, service: Service) -> PieceDetail:
    await service.publish_piece(piece_id)
    piece, _ = await service.get_detail(piece_id)
    return PieceDetail.from_piece(piece)


# ============================================================== admin: media
@admin_router.post(
    "/pieces/{piece_id}/media", response_model=MediaOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CATALOGUE_WRITE))],
)
async def add_media(
    piece_id: uuid.UUID,
    service: Service,
    file: Annotated[UploadFile, File(description="Image file (jpeg/png/webp)")],
    view_label: Annotated[str | None, Form()] = None,
    position: Annotated[int, Form()] = 0,
) -> MediaOut:
    data = await file.read()
    media = await service.add_media(
        piece_id,
        data=data,
        content_type=file.content_type or "application/octet-stream",
        meta=MediaMeta(view_label=view_label, position=position),
    )
    return MediaOut.model_validate(media)


@admin_router.delete(
    "/pieces/{piece_id}/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permission.CATALOGUE_WRITE))],
)
async def remove_media(
    piece_id: uuid.UUID, media_id: uuid.UUID, service: Service
) -> Response:
    await service.remove_media(piece_id, media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ================================================== admin: publication batches
@admin_router.post(
    "/publication-batches", response_model=PublicationBatchOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CATALOGUE_PUBLISH))],
)
async def create_batch(
    payload: PublicationBatchCreate, service: Service, user: CurrentUser
) -> PublicationBatchOut:
    batch = await service.create_batch(payload, published_by=user.id)
    return PublicationBatchOut.model_validate(batch)


@admin_router.get(
    "/publication-batches", response_model=list[PublicationBatchOut],
    dependencies=[Depends(require_permission(Permission.CATALOGUE_READ))],
)
async def list_batches(service: Service) -> list[PublicationBatchOut]:
    return [PublicationBatchOut.model_validate(b) for b in await service.list_batches()]