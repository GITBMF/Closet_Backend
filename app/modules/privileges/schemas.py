"""Privilege-code request/response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.privileges.constants import PrivilegeType


class PrivilegeCodeCreate(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    type: PrivilegeType
    value: Decimal = Field(gt=0)
    min_order_amount: Decimal | None = Field(default=None, ge=0)
    max_uses: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool = True


class PrivilegeCodeUpdate(BaseModel):
    value: Decimal | None = Field(default=None, gt=0)
    min_order_amount: Decimal | None = Field(default=None, ge=0)
    max_uses: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool | None = None


class PrivilegeCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    type: PrivilegeType
    value: Decimal
    min_order_amount: Decimal | None
    max_uses: int | None
    times_used: int
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    created_at: datetime


class PrivilegeCheckIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    subtotal: Decimal = Field(ge=0)


class PrivilegeCheckOut(BaseModel):
    valid: bool
    code: str
    discount_amount: Decimal = Decimal(0)
    type: PrivilegeType | None = None
    reason: str | None = None
