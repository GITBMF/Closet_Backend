"""Privilege-code endpoints.

Admin: create / list / update discount codes (admin-only).
Public: POST /privileges/check — validate a code + preview the discount before
checkout (does not redeem it).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.modules.identity.constants import UserRole
from app.modules.identity.dependencies import CurrentUser, require_role
from app.modules.privileges.dependencies import Service
from app.modules.privileges.schemas import (
    PrivilegeCheckIn,
    PrivilegeCheckOut,
    PrivilegeCodeCreate,
    PrivilegeCodeOut,
    PrivilegeCodeUpdate,
)

_ADMIN = Depends(require_role(UserRole.ADMIN))

admin_router = APIRouter(
    prefix="/admin/privileges", tags=["privileges-admin"], dependencies=[_ADMIN]
)


@admin_router.post("", response_model=PrivilegeCodeOut, status_code=201)
async def create_code(
    payload: PrivilegeCodeCreate, service: Service, user: CurrentUser
) -> PrivilegeCodeOut:
    obj = await service.create_code(payload, created_by=user.id)
    return PrivilegeCodeOut.model_validate(obj)


@admin_router.get("", response_model=list[PrivilegeCodeOut])
async def list_codes(service: Service) -> list[PrivilegeCodeOut]:
    return [PrivilegeCodeOut.model_validate(c) for c in await service.list_codes()]


@admin_router.patch("/{code_id}", response_model=PrivilegeCodeOut)
async def update_code(
    code_id: uuid.UUID, payload: PrivilegeCodeUpdate, service: Service
) -> PrivilegeCodeOut:
    return PrivilegeCodeOut.model_validate(await service.update_code(code_id, payload))


router = APIRouter(prefix="/privileges", tags=["privileges"])


@router.post("/check", response_model=PrivilegeCheckOut)
async def check_code(payload: PrivilegeCheckIn, service: Service) -> PrivilegeCheckOut:
    valid, discount, ctype, reason = await service.check(payload.code, payload.subtotal)
    return PrivilegeCheckOut(
        valid=valid,
        code=payload.code.strip().upper(),
        discount_amount=discount,
        type=ctype,
        reason=reason,
    )
