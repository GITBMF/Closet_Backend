"""Payment HTTP layer.

  * router       -> /payments/*        initiate, poll, provider webhook (public)
  * admin_router -> /admin/payments/*   list, reconcile, refund (admin)

The webhook is public by necessity (the provider calls it server-to-server) but
is protected by signature verification inside the service, not by auth. It
always returns 200 so the provider stops retrying once we've received it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.modules.identity.constants import Permission
from app.modules.identity.dependencies import CurrentUser, require_permission
from app.modules.payments.constants import PaymentStatus
from app.modules.payments.dependencies import Service
from app.modules.payments.schemas import (
    InitiateIn,
    InitiateOut,
    PaymentOut,
    PaymentsPage,
    PaymentSummary,
    ReconcileIn,
    RefundIn,
    RefundOut,
    WebhookAck,
)

router = APIRouter(prefix="/payments", tags=["payments"])
admin_router = APIRouter(prefix="/admin/payments", tags=["admin: payments"])


# ================================================================= public
@router.post("/initiate", response_model=InitiateOut, status_code=status.HTTP_201_CREATED)
async def initiate_payment(payload: InitiateIn, service: Service) -> InitiateOut:
    payment = await service.initiate(payload)
    return InitiateOut(
        id=payment.id,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        payment_url=getattr(payment, "_payment_url", None),
        provider_reference=payment.provider_reference,
    )


@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(payment_id: uuid.UUID, service: Service) -> PaymentOut:
    return PaymentOut.model_validate(await service.get(payment_id))


@router.post("/webhook/cinetpay", response_model=WebhookAck)
async def cinetpay_webhook(request: Request, service: Service) -> WebhookAck:
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    # never trusts the body: the service verifies the signature first and does
    # nothing on a bad one. Always ack so the provider stops retrying.
    await service.handle_webhook(raw_body=raw, headers=headers)
    return WebhookAck()


# ================================================================== admin
@admin_router.get(
    "",
    response_model=PaymentsPage,
    dependencies=[Depends(require_permission(Permission.PAYMENT_RECONCILE))],
)
async def list_payments(
    service: Service,
    status_filter: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaymentsPage:
    items, total = await service.list_all(
        status=status_filter, limit=limit, offset=offset
    )
    return PaymentsPage(
        items=[PaymentSummary.model_validate(p) for p in items],
        total=total, limit=limit, offset=offset,
    )


@admin_router.post(
    "/{payment_id}/reconcile",
    response_model=PaymentOut,
    dependencies=[Depends(require_permission(Permission.PAYMENT_RECONCILE))],
)
async def reconcile_payment(
    payment_id: uuid.UUID, payload: ReconcileIn, service: Service, user: CurrentUser
) -> PaymentOut:
    return PaymentOut.model_validate(
        await service.reconcile(payment_id, payload, admin_id=user.id)
    )


@admin_router.post(
    "/{payment_id}/refund",
    response_model=RefundOut,
    dependencies=[Depends(require_permission(Permission.PAYMENT_REFUND))],
)
async def refund_payment(
    payment_id: uuid.UUID, payload: RefundIn, service: Service, user: CurrentUser
) -> RefundOut:
    return RefundOut.model_validate(
        await service.refund(payment_id, payload, admin_id=user.id)
    )