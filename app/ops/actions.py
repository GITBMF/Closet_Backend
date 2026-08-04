"""Service-backed admin actions.

These are the ONLY write path for the business-rule models. Each action opens a
fresh AsyncSession and calls the same service method the public API uses, so
every state machine, permission check, and cross-module effect (grant role,
issue refund, restock, create piece) is preserved. Hand-editing those tables is
disabled in the ModelViews, so operators can only move state through these.

Handlers return a short success string (shown to the operator) or raise
ActionFailed(message) to surface a meaningful error.

Signatures were verified against the current codebase:
  orders.update_status(order_id, StatusUpdate, *, admin_id)   [no internal commit]
  orders.cancel(order_id, *, reason, actor_type)
  payments.reconcile(payment_id, ReconcileIn, *, admin_id)    [no internal commit]
  payments.refund(payment_id, RefundIn, *, admin_id)          [no internal commit]
  catalogue.publish_piece(piece_id)                           [commits internally]
  identity.admin_change_role(*, admin, user_id, role, reason, ctx)
  identity.admin_set_active(*, admin, user_id, is_active, ctx)
  sourcing.approve_application / reject_application / decide / catalogue_submission
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from starlette.requests import Request
from starlette_admin.exceptions import ActionFailed

from app.core.database import AsyncSessionLocal
from app.core.exceptions import AppError


def _admin_user(request: Request):
    user = getattr(request.state, "user", None)
    if user is None:
        raise ActionFailed("Not authenticated.")
    return user


def _admin_id(request: Request) -> uuid.UUID:
    return _admin_user(request).id


def _ctx(request: Request):
    from app.modules.identity.service import RequestContext
    fwd = request.headers.get("x-forwarded-for")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
    return RequestContext(ip=ip, user_agent=request.headers.get("user-agent"))


def _pk(pk) -> uuid.UUID:
    return pk if isinstance(pk, uuid.UUID) else uuid.UUID(str(pk))


def _amount(raw: str) -> Decimal:
    try:
        return Decimal(raw)
    except (InvalidOperation, TypeError):
        raise ActionFailed("Enter a valid amount.")


# ------------------------------------------------------------------ sourcing
async def sourcer_approve(request: Request, pk) -> str:
    from app.modules.sourcing.dependencies import get_sourcing_service
    try:
        async with AsyncSessionLocal() as db:
            await get_sourcing_service(db).approve_application(_pk(pk), admin_id=_admin_id(request))
        return "Sourcer approved — role granted."
    except AppError as e:
        raise ActionFailed(str(e))


async def sourcer_reject(request: Request, pk, reason: str) -> str:
    from app.modules.sourcing.dependencies import get_sourcing_service
    if not reason:
        raise ActionFailed("A reason is required to reject.")
    try:
        async with AsyncSessionLocal() as db:
            await get_sourcing_service(db).reject_application(_pk(pk), reason=reason, admin_id=_admin_id(request))
        return "Application rejected."
    except AppError as e:
        raise ActionFailed(str(e))


async def submission_decide(request: Request, pk, accept: bool, reason: str | None) -> str:
    from app.modules.sourcing.dependencies import get_sourcing_service
    from app.modules.sourcing.schemas import DecisionIn
    try:
        async with AsyncSessionLocal() as db:
            await get_sourcing_service(db).decide(
                _pk(pk), DecisionIn(accept=accept, reason=reason), admin_id=_admin_id(request)
            )
        return "Submission accepted." if accept else "Submission refused."
    except AppError as e:
        raise ActionFailed(str(e))


async def submission_catalogue(request: Request, pk, title: str, price: str, condition: str) -> str:
    from app.modules.sourcing.dependencies import get_sourcing_service
    from app.modules.sourcing.schemas import CatalogueIn
    if not title:
        raise ActionFailed("A title is required.")
    try:
        async with AsyncSessionLocal() as db:
            await get_sourcing_service(db).catalogue_submission(
                _pk(pk),
                CatalogueIn(title=title, price=_amount(price), condition=condition),
                admin_id=_admin_id(request),
            )
        return "Submission catalogued — piece created."
    except AppError as e:
        raise ActionFailed(str(e))


# -------------------------------------------------------------------- orders
async def order_update_status(request: Request, pk, status: str, reason: str | None) -> str:
    from app.modules.orders.dependencies import get_order_service
    from app.modules.orders.schemas import StatusUpdate
    from app.modules.orders.constants import OrderStatus
    try:
        async with AsyncSessionLocal() as db:
            svc = get_order_service(db)
            await svc.update_status(
                _pk(pk), StatusUpdate(status=OrderStatus(status), reason=reason),
                admin_id=_admin_id(request),
            )
            await db.commit()
        return f"Order moved to {status}."
    except (AppError, ValueError) as e:
        raise ActionFailed(str(e))


async def order_cancel(request: Request, pk, reason: str) -> str:
    from app.modules.orders.dependencies import get_order_service
    from app.modules.identity.constants import ActorType
    if not reason:
        raise ActionFailed("A cancellation reason is required.")
    try:
        async with AsyncSessionLocal() as db:
            svc = get_order_service(db)
            await svc.cancel(_pk(pk), reason=reason, actor_type=ActorType.ADMIN)
            await db.commit()
        return "Order cancelled."
    except (AppError, ValueError, AttributeError) as e:
        raise ActionFailed(str(e))


# ------------------------------------------------------------------ payments
async def payment_reconcile(request: Request, pk, status: str, note: str | None) -> str:
    from app.modules.payments.dependencies import get_payment_service
    from app.modules.payments.schemas import ReconcileIn
    from app.modules.payments.constants import PaymentStatus
    try:
        async with AsyncSessionLocal() as db:
            svc = get_payment_service(db)
            await svc.reconcile(
                _pk(pk), ReconcileIn(status=PaymentStatus(status), note=note),
                admin_id=_admin_id(request),
            )
            await db.commit()
        return f"Payment marked {status}."
    except (AppError, ValueError) as e:
        raise ActionFailed(str(e))


async def payment_refund(request: Request, pk, amount: str, reason: str | None) -> str:
    from app.modules.payments.dependencies import get_payment_service
    from app.modules.payments.schemas import RefundIn
    try:
        async with AsyncSessionLocal() as db:
            svc = get_payment_service(db)
            await svc.refund(
                _pk(pk), RefundIn(amount=_amount(amount), reason=reason),
                admin_id=_admin_id(request),
            )
            await db.commit()
        return f"Refund of {amount} issued."
    except AppError as e:
        raise ActionFailed(str(e))


# ----------------------------------------------------------------- catalogue
async def piece_publish(request: Request, pk) -> str:
    from app.modules.catalogue.dependencies import get_catalogue_service
    try:
        async with AsyncSessionLocal() as db:
            await get_catalogue_service(db).publish_piece(_pk(pk))  # commits internally
        return "Piece published."
    except AppError as e:
        raise ActionFailed(str(e))


# --------------------------------------------------------------------- users
async def user_change_role(request: Request, pk, role: str, reason: str | None) -> str:
    from app.modules.identity.dependencies import get_identity_service
    from app.modules.identity.constants import UserRole
    try:
        async with AsyncSessionLocal() as db:
            svc = get_identity_service(db)
            await svc.admin_change_role(
                admin=_admin_user(request), user_id=_pk(pk),
                role=UserRole(role), reason=reason, ctx=_ctx(request),
            )
            await db.commit()
        return f"Role changed to {role}."
    except (AppError, ValueError) as e:
        raise ActionFailed(str(e))


async def user_set_active(request: Request, pk, is_active: bool) -> str:
    from app.modules.identity.dependencies import get_identity_service
    try:
        async with AsyncSessionLocal() as db:
            svc = get_identity_service(db)
            await svc.admin_set_active(
                admin=_admin_user(request), user_id=_pk(pk),
                is_active=is_active, ctx=_ctx(request),
            )
            await db.commit()
        return "User activated." if is_active else "User deactivated."
    except AppError as e:
        raise ActionFailed(str(e))