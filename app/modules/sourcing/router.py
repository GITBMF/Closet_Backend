"""Sourcing HTTP layer — the supplier side.

  * router       -> /sourcing/*          customer/sourcer (JWT)
  * admin_router -> /admin/sourcing/*     review + approvals

Customer routes resolve the sourcer from the JWT user. Admin routes are guarded
by the sourcing permissions from identity/constants.py.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import CurrentUser, require_permission
from app.modules.sourcing.constants import SourcerStatus, SubmissionStatus
from app.modules.sourcing.dependencies import Service
from app.modules.sourcing.schemas import (
    ApplyIn,
    CatalogueIn,
    DecisionIn,
    MediaIn,
    MediaOut,
    PayoutOut,
    RejectIn,
    SourcerProfileOut,
    SubmissionCreate,
    SubmissionOut,
    SubmissionsPage,
    SubmissionSummary,
)

router = APIRouter(prefix="/sourcing", tags=["sourcing"])
admin_router = APIRouter(prefix="/admin/sourcing", tags=["admin: sourcing"])

_CREATE = Depends(require_permission(Permission.SUBMISSION_CREATE))
_READ_OWN = Depends(require_permission(Permission.SUBMISSION_READ_OWN))
_PAYOUT_OWN = Depends(require_permission(Permission.PAYOUT_READ_OWN))
_REVIEW = Depends(require_permission(Permission.SUBMISSION_REVIEW))
_APPROVE = Depends(require_permission(Permission.SOURCER_APPROVE))


def _page(items, total, limit, offset) -> SubmissionsPage:
    return SubmissionsPage(
        items=[SubmissionSummary.model_validate(s) for s in items],
        total=total, limit=limit, offset=offset,
    )


# ================================================ customer: application
@router.post("/apply", response_model=SourcerProfileOut,
             status_code=status.HTTP_201_CREATED)
async def apply(payload: ApplyIn, service: Service, user: CurrentUser) -> SourcerProfileOut:
    return SourcerProfileOut.model_validate(await service.apply(user.id, payload))


@router.get("/me", response_model=SourcerProfileOut)
async def my_profile(service: Service, user: CurrentUser) -> SourcerProfileOut:
    return SourcerProfileOut.model_validate(await service.my_profile(user.id))


# ================================================ customer: submissions
@router.post("/submissions", response_model=SubmissionOut,
             status_code=status.HTTP_201_CREATED, dependencies=[_CREATE])
async def create_submission(
    payload: SubmissionCreate, service: Service, user: CurrentUser
) -> SubmissionOut:
    return SubmissionOut.model_validate(await service.create_submission(user.id, payload))


@router.get("/submissions", response_model=SubmissionsPage, dependencies=[_READ_OWN])
async def my_submissions(
    service: Service, user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SubmissionsPage:
    items, total = await service.my_submissions(user.id, limit=limit, offset=offset)
    return _page(items, total, limit, offset)


@router.get("/submissions/{submission_id}", response_model=SubmissionOut,
            dependencies=[_READ_OWN])
async def my_submission(
    submission_id: uuid.UUID, service: Service, user: CurrentUser
) -> SubmissionOut:
    return SubmissionOut.model_validate(await service.my_submission(user.id, submission_id))


@router.post("/submissions/{submission_id}/media", response_model=MediaOut,
             status_code=status.HTTP_201_CREATED, dependencies=[_CREATE])
async def add_media(
    submission_id: uuid.UUID, payload: MediaIn, service: Service, user: CurrentUser
) -> MediaOut:
    return MediaOut.model_validate(await service.add_media(user.id, submission_id, payload))


@router.get("/payouts", response_model=list[PayoutOut], dependencies=[_PAYOUT_OWN])
async def my_payouts(service: Service, user: CurrentUser) -> list[PayoutOut]:
    return [PayoutOut.model_validate(p) for p in await service.my_payouts(user.id)]


# ============================================== admin: applications
@admin_router.get("/applications", response_model=list[SourcerProfileOut],
                  dependencies=[_APPROVE])
async def list_applications(
    service: Service,
    status_filter: Annotated[SourcerStatus | None, Query(alias="status")] = SourcerStatus.PENDING,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SourcerProfileOut]:
    items, _ = await service.list_applications(
        status=status_filter, limit=limit, offset=offset
    )
    return [SourcerProfileOut.model_validate(p) for p in items]


@admin_router.post("/applications/{profile_id}/approve",
                   response_model=SourcerProfileOut, dependencies=[_APPROVE])
async def approve_application(
    profile_id: uuid.UUID, service: Service, user: CurrentUser
) -> SourcerProfileOut:
    return SourcerProfileOut.model_validate(
        await service.approve_application(profile_id, admin_id=user.id)
    )


@admin_router.post("/applications/{profile_id}/reject",
                   response_model=SourcerProfileOut, dependencies=[_APPROVE])
async def reject_application(
    profile_id: uuid.UUID, payload: RejectIn, service: Service, user: CurrentUser
) -> SourcerProfileOut:
    return SourcerProfileOut.model_validate(
        await service.reject_application(profile_id, reason=payload.reason, admin_id=user.id)
    )


# ================================================== admin: review
@admin_router.get("/submissions", response_model=SubmissionsPage, dependencies=[_REVIEW])
async def review_queue(
    service: Service,
    status_filter: Annotated[SubmissionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SubmissionsPage:
    items, total = await service.list_review_queue(
        status=status_filter, limit=limit, offset=offset
    )
    return _page(items, total, limit, offset)


@admin_router.get("/submissions/{submission_id}", response_model=SubmissionOut,
                  dependencies=[_REVIEW])
async def review_detail(submission_id: uuid.UUID, service: Service) -> SubmissionOut:
    return SubmissionOut.model_validate(await service.get_for_review(submission_id))


@admin_router.post("/submissions/{submission_id}/decision",
                   response_model=SubmissionOut, dependencies=[_REVIEW])
async def decide(
    submission_id: uuid.UUID, payload: DecisionIn, service: Service, user: CurrentUser
) -> SubmissionOut:
    return SubmissionOut.model_validate(
        await service.decide(submission_id, payload, admin_id=user.id)
    )


@admin_router.post("/submissions/{submission_id}/catalogue",
                   response_model=SubmissionOut, dependencies=[_REVIEW])
async def catalogue_submission(
    submission_id: uuid.UUID, payload: CatalogueIn, service: Service, user: CurrentUser
) -> SubmissionOut:
    return SubmissionOut.model_validate(
        await service.catalogue_submission(submission_id, payload, admin_id=user.id)
    )