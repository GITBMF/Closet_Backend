"""Privilege-code business logic: create/list/update, validate, and redeem.

Validation is shared by the public "check" endpoint (never raises) and the
checkout "apply" path (raises so an invalid code stops checkout with a clear
message). Redemption records a row and atomically bumps the usage counter.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.privileges.constants import PrivilegeType
from app.modules.privileges.models import PrivilegeCode, PrivilegeRedemption
from app.modules.privileges.repository import PrivilegeRepository
from app.modules.privileges.schemas import PrivilegeCodeCreate, PrivilegeCodeUpdate


def _norm(code: str) -> str:
    return code.strip().upper()


def _q(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PrivilegeService:
    def __init__(self, repo: PrivilegeRepository) -> None:
        self.repo = repo

    # ---------------------------------------------------------------- admin
    async def create_code(
        self, payload: PrivilegeCodeCreate, *, created_by: uuid.UUID | None
    ) -> PrivilegeCode:
        code = _norm(payload.code)
        if await self.repo.get_by_code(code) is not None:
            raise ConflictError("Ce code existe déjà.", code="code_exists")
        if payload.type is PrivilegeType.PERCENTAGE and payload.value > Decimal(100):
            raise ValidationError(
                "Un pourcentage ne peut pas dépasser 100.", code="percentage_too_high"
            )
        obj = await self.repo.add(
            PrivilegeCode(
                code=code,
                type=payload.type,
                value=payload.value,
                min_order_amount=payload.min_order_amount,
                max_uses=payload.max_uses,
                valid_from=payload.valid_from,
                valid_until=payload.valid_until,
                is_active=payload.is_active,
                created_by=created_by,
            )
        )
        await self.repo.db.commit()
        return obj

    async def list_codes(self) -> list[PrivilegeCode]:
        return await self.repo.list_codes()

    async def update_code(
        self, code_id: uuid.UUID, payload: PrivilegeCodeUpdate
    ) -> PrivilegeCode:
        obj = await self.repo.get(code_id)
        if obj is None:
            raise NotFoundError("Code introuvable.", code="code_not_found")
        data = payload.model_dump(exclude_unset=True)
        new_value = data.get("value", obj.value)
        if obj.type is PrivilegeType.PERCENTAGE and Decimal(str(new_value)) > Decimal(100):
            raise ValidationError(
                "Un pourcentage ne peut pas dépasser 100.", code="percentage_too_high"
            )
        for key, val in data.items():
            setattr(obj, key, val)
        await self.repo.db.commit()
        return obj

    # ------------------------------------------------------------ validate
    def _discount_for(self, code: PrivilegeCode, subtotal: Decimal) -> Decimal:
        if code.type is PrivilegeType.PERCENTAGE:
            disc = subtotal * (Decimal(code.value) / Decimal(100))
        else:
            disc = Decimal(code.value)
        return _q(min(disc, subtotal))  # never discount more than the subtotal

    async def _validated(
        self, code_str: str, subtotal: Decimal
    ) -> tuple[PrivilegeCode, Decimal]:
        code = await self.repo.get_by_code(_norm(code_str))
        if code is None:
            raise ValidationError("Code inconnu.", code="code_unknown")
        if not code.is_active:
            raise ValidationError("Ce code n'est plus actif.", code="code_inactive")
        now = datetime.now(UTC)
        if code.valid_from and now < code.valid_from:
            raise ValidationError("Ce code n'est pas encore valide.", code="code_not_started")
        if code.valid_until and now > code.valid_until:
            raise ValidationError("Ce code a expiré.", code="code_expired")
        if code.max_uses is not None and code.times_used >= code.max_uses:
            raise ValidationError(
                "Ce code a atteint sa limite d'utilisation.", code="code_exhausted"
            )
        if code.min_order_amount is not None and subtotal < Decimal(code.min_order_amount):
            raise ValidationError(
                "Le montant minimum pour ce code n'est pas atteint.",
                code="min_order_not_met",
            )
        return code, self._discount_for(code, subtotal)

    async def check(
        self, code_str: str, subtotal: Decimal
    ) -> tuple[bool, Decimal, PrivilegeType | None, str | None]:
        """Non-raising validation for a pre-checkout check."""
        try:
            code, disc = await self._validated(code_str, subtotal)
            return True, disc, code.type, None
        except ValidationError as exc:
            return False, Decimal(0), None, str(exc)

    async def apply(
        self, code_str: str, subtotal: Decimal
    ) -> tuple[PrivilegeCode, Decimal]:
        """Validate at checkout; raises ValidationError if the code isn't usable."""
        return await self._validated(code_str, subtotal)

    async def redeem(
        self,
        code: PrivilegeCode,
        *,
        purchase_id: uuid.UUID,
        user_id: uuid.UUID | None,
        amount: Decimal,
    ) -> None:
        await self.repo.add_redemption(
            PrivilegeRedemption(
                code_id=code.id,
                purchase_id=purchase_id,
                user_id=user_id,
                amount=_q(amount),
            )
        )
        await self.repo.increment_usage(code.id)
