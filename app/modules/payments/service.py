"""Payment service — orchestration and the webhook state machine.

This is the module that "needs the most care" (per the work-split doc). Two
guarantees dominate the design:

  * IDEMPOTENCY. Initiating twice for the same order attempt returns the same
    payment (unique idempotency_key). A retried webhook is recorded and acted
    on once (unique provider_event_id). Providers retry; we must not double-pay
    or double-confirm.

  * SIGNATURE-FIRST. A webhook body is never trusted until its signature checks
    out. An invalid signature is recorded (signature_valid=False) and changes
    NOTHING — no payment update, no order transition.

On a confirmed payment the service calls orders.mark_paid(); on a definitive
failure it calls orders.cancel(). It reaches orders only through OrderService —
never its repository or tables. All writes for one webhook commit together.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.identity.constants import ActorType
from app.modules.orders.service import OrderService
from app.modules.payments.constants import PaymentStatus
from app.modules.payments.models import Payment, PaymentEvent, Refund
from app.modules.payments.providers.base import (
    InitiateRequest,
    PaymentProvider,
    PaymentProviderError,
)
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import InitiateIn, ReconcileIn, RefundIn

_CENTS = Decimal("0.01")


def _q(amount) -> Decimal:
    return Decimal(amount).quantize(_CENTS)


class PaymentService:
    def __init__(
        self,
        repo: PaymentRepository,
        orders: OrderService,
        provider: PaymentProvider,
        *,
        currency: str,
        return_url: str,
        notify_url: str,
    ) -> None:
        self.repo = repo
        self.orders = orders
        self.provider = provider
        self.currency = currency
        self.return_url = return_url
        self.notify_url = notify_url

    @property
    def db(self):
        return self.repo.db

    # ============================================================ initiate
    async def initiate(self, payload: InitiateIn) -> Payment:
        order = await self.orders.get_by_number(payload.order_number)

        if order.status is not None and order.status.value != "pending":
            # only a pending order can be paid; paid/cancelled/etc. cannot
            raise ConflictError(
                "Cette commande n'est pas en attente de paiement.",
                code="order_not_payable",
            )

        # idempotency: one active attempt per order. Reuse an existing
        # initiated/pending payment instead of opening a second one.
        existing = await self.repo.latest_for_purchase(order.id)
        if existing is not None and existing.status in (
            PaymentStatus.INITIATED,
            PaymentStatus.PENDING,
        ):
            return existing

        provider_row = await self.repo.ensure_provider(
            self.provider.code, self.provider.code.title()
        )

        amount = _q(order.total)
        # idempotency key ties the provider transaction to this order attempt
        idem = f"{order.order_number}:{uuid.uuid4().hex[:8]}"

        payment = Payment(
            purchase_id=order.id,
            provider_id=provider_row.id,
            operator=payload.operator,
            amount=amount,
            currency=self.currency,
            status=PaymentStatus.INITIATED,
            idempotency_key=idem,
            payer_phone=payload.customer_phone or order.customer_phone,
            initiated_at=datetime.now(UTC),
        )
        await self.repo.add_payment(payment)

        req = InitiateRequest(
            amount=amount,
            currency=self.currency,
            reference=idem,
            description=f"ClosET {order.order_number}",
            customer_name=order.customer_name,
            customer_phone=payload.customer_phone or order.customer_phone,
            customer_email=payload.customer_email or order.customer_email,
            return_url=self.return_url,
            notify_url=self.notify_url,
            metadata={"order_number": order.order_number},
        )
        try:
            result = await self.provider.initiate(req)
        except PaymentProviderError as exc:
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = exc.message
            await self.db.commit()
            raise

        payment.provider_reference = result.provider_reference
        payment.status = PaymentStatus.PENDING
        # stash the hosted URL on the object for the response (not persisted)
        payment._payment_url = result.payment_url  # type: ignore[attr-defined]
        await self.db.commit()
        refreshed = await self.repo.get(payment.id)
        refreshed._payment_url = result.payment_url  # type: ignore[attr-defined]
        return refreshed

    # --------------------------------------------------------------- reads
    async def get(self, payment_id: uuid.UUID) -> Payment:
        payment = await self.repo.get(payment_id)
        if payment is None:
            raise NotFoundError("Paiement introuvable.", code="payment_not_found")
        return payment

    async def list_all(self, *, status, limit, offset):
        return await self.repo.list_all(status=status, limit=limit, offset=offset)

    # =============================================================== webhook
    async def handle_webhook(
        self, *, raw_body: bytes, headers: dict[str, str]
    ) -> None:
        """Process a provider callback. Always safe to call repeatedly.

        Order of operations is deliberate:
          1. parse + verify signature (never trust the body first)
          2. dedupe by provider_event_id (retries are no-ops)
          3. match to a payment by provider_reference
          4. record the event
          5. only if the signature was valid: apply the state change and, on
             success/failure, drive the order via OrderService
          6. commit everything together
        """
        result = self.provider.parse_webhook(raw_body=raw_body, headers=headers)

        # 2. idempotent on provider_event_id
        if result.provider_event_id and await self.repo.event_exists(
            result.provider_event_id
        ):
            return  # already processed; ack without acting

        # 3. find the payment this refers to
        payment = None
        if result.provider_reference:
            payment = await self.repo.get_by_provider_reference(
                result.provider_reference
            )
            if payment is None:
                payment = await self.repo.get_by_idempotency_key(
                    result.provider_reference
                )

        # 4. record the raw event (audit + idempotency), linked if we found one
        if payment is not None:
            event = PaymentEvent(
                payment_id=payment.id,
                provider_event_id=result.provider_event_id,
                event_type=result.event_type,
                payload=result.payload,
                signature_valid=result.signature_valid,
                processing_error=result.error,
            )
            await self.repo.add_event(event)

        # 5. a bad signature changes nothing
        if not result.signature_valid:
            await self.db.commit()
            return
        if payment is None or result.status is None:
            await self.db.commit()
            return

        await self._apply_status(payment, result.status)
        await self.db.commit()

    async def _apply_status(self, payment: Payment, status: PaymentStatus) -> None:
        # ignore terminal-state transitions (already succeeded/failed)
        if payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED):
            return

        if status is PaymentStatus.SUCCEEDED:
            payment.status = PaymentStatus.SUCCEEDED
            payment.confirmed_at = datetime.now(UTC)
            # drive the order: PENDING -> PAID, sells the reserved pieces
            await self.orders.mark_paid(payment.purchase_id)
        elif status is PaymentStatus.FAILED:
            payment.status = PaymentStatus.FAILED
            # release the held pieces so the order doesn't sit on stock
            await self.orders.cancel(
                payment.purchase_id,
                reason="payment failed",
                actor_type=ActorType.SYSTEM,
            )
        else:
            payment.status = PaymentStatus.PENDING

    # ------------------------------------------------------ admin: reconcile
    async def reconcile(
        self, payment_id: uuid.UUID, payload: ReconcileIn, *, admin_id: uuid.UUID
    ) -> Payment:
        """Manually settle a payment after an out-of-band check with the provider."""
        payment = await self.get(payment_id)
        if payload.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED):
            raise ValidationError(
                "Le rapprochement n'accepte que 'succeeded' ou 'failed'.",
                code="bad_reconcile_status",
            )
        event = PaymentEvent(
            payment_id=payment.id,
            provider_event_id=f"manual:{uuid.uuid4().hex}",
            event_type="manual_reconcile",
            payload={"note": payload.note, "by": str(admin_id)},
            signature_valid=True,
        )
        await self.repo.add_event(event)
        payment.reconciled_at = datetime.now(UTC)
        await self._apply_status(payment, payload.status)
        await self.db.commit()
        return await self.repo.get(payment.id)

    # --------------------------------------------------------- admin: refund
    async def refund(
        self, payment_id: uuid.UUID, payload: RefundIn, *, admin_id: uuid.UUID
    ) -> Refund:
        payment = await self.get(payment_id)
        if payment.status not in (
            PaymentStatus.SUCCEEDED,
            PaymentStatus.PARTIALLY_REFUNDED,
        ):
            raise ConflictError(
                "Seul un paiement abouti peut être remboursé.",
                code="not_refundable",
            )
        amount = _q(payload.amount)
        already = _q(await self.repo.total_refunded(payment.id))
        if already + amount > _q(payment.amount):
            raise ValidationError(
                "Le remboursement dépasse le montant payé.",
                code="refund_exceeds_payment",
            )

        try:
            result = await self.provider.refund(
                provider_reference=payment.provider_reference or "",
                amount=amount,
                reason=payload.reason,
            )
            provider_ref = result.provider_reference
        except PaymentProviderError:
            # provider can't auto-refund (common for mobile money) — still record
            # the refund as issued; settlement happens manually out of band.
            provider_ref = None

        refund = Refund(
            payment_id=payment.id,
            amount=amount,
            reason=payload.reason,
            provider_reference=provider_ref,
            created_by=admin_id,
        )
        await self.repo.add_refund(refund)

        new_total = already + amount
        payment.status = (
            PaymentStatus.REFUNDED
            if new_total >= _q(payment.amount)
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        await self.db.commit()
        return refund