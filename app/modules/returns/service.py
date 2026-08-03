"""Returns service — the post-sale return workflow.

A customer who received an order requests to return a specific piece. An admin
reviews. On approve the customer is refunded (via the payments service); on
resolve the piece is optionally restocked (via the catalogue service). Cross-
module work always goes through those SERVICES, on the same session, so a
decision and its money/stock effect commit together.

State machine:
  requested -> approved -> resolved
            -> rejected
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.modules.catalogue.service import CatalogueService
from app.modules.orders.constants import OrderStatus
from app.modules.orders.service import OrderService
from app.modules.payments.schemas import RefundIn
from app.modules.payments.service import PaymentService
from app.modules.returns.constants import ReturnStatus
from app.modules.returns.models import ReturnTicket
from app.modules.returns.repository import ReturnsRepository
from app.modules.returns.schemas import (
    ApproveIn,
    RejectIn,
    ResolveIn,
    ReturnCreate,
)

# an order is returnable once the customer has it
_RETURNABLE = {OrderStatus.COMPLETED, OrderStatus.DELIVERING}

_TRANSITIONS: dict[ReturnStatus, set[ReturnStatus]] = {
    ReturnStatus.REQUESTED: {ReturnStatus.APPROVED, ReturnStatus.REJECTED},
    ReturnStatus.APPROVED: {ReturnStatus.RESOLVED},
    ReturnStatus.REJECTED: set(),
    ReturnStatus.RESOLVED: set(),
}


class ReturnsService:
    def __init__(
        self,
        repo: ReturnsRepository,
        orders: OrderService,
        payments: PaymentService,
        catalogue: CatalogueService,
    ) -> None:
        self.repo = repo
        self.orders = orders
        self.payments = payments
        self.catalogue = catalogue

    @property
    def db(self):
        return self.repo.db

    # =============================================== customer: request
    async def request_return(
        self, user_id: uuid.UUID, payload: ReturnCreate
    ) -> ReturnTicket:
        order = await self.orders.get_admin(payload.purchase_id)  # loads items
        if order.user_id != user_id:
            # don't reveal existence of others' orders
            raise NotFoundError("Commande introuvable.", code="order_not_found")
        if order.status not in _RETURNABLE:
            raise ConflictError(
                "Cette commande n'est pas éligible à un retour.",
                code="order_not_returnable",
            )
        # the piece must belong to this order
        piece_ids = {item.piece_id for item in order.items}
        if payload.piece_id not in piece_ids:
            raise ValidationError(
                "Cet article ne fait pas partie de la commande.",
                code="piece_not_in_order",
            )
        # no duplicate open ticket
        if await self.repo.open_ticket_for(payload.purchase_id, payload.piece_id):
            raise ConflictError(
                "Un retour est déjà en cours pour cet article.",
                code="return_exists",
            )
        ticket = ReturnTicket(
            purchase_id=payload.purchase_id,
            piece_id=payload.piece_id,
            reason=payload.reason,
            status=ReturnStatus.REQUESTED,
            created_by=user_id,
        )
        await self.repo.add(ticket)
        await self.db.commit()
        return await self.repo.get(ticket.id)

    async def my_returns(self, user_id: uuid.UUID, *, limit: int, offset: int):
        return await self.repo.list_for_user(user_id, limit=limit, offset=offset)

    async def my_return(self, user_id: uuid.UUID, ticket_id: uuid.UUID) -> ReturnTicket:
        ticket = await self.repo.get(ticket_id)
        if ticket is None:
            raise NotFoundError("Retour introuvable.", code="return_not_found")
        order = await self.orders.get_admin(ticket.purchase_id)
        if order.user_id != user_id:
            raise NotFoundError("Retour introuvable.", code="return_not_found")
        return ticket

    # ================================================== admin: review
    async def list_all(self, *, status, limit, offset):
        return await self.repo.list_all(status=status, limit=limit, offset=offset)

    async def get(self, ticket_id: uuid.UUID) -> ReturnTicket:
        ticket = await self.repo.get(ticket_id)
        if ticket is None:
            raise NotFoundError("Retour introuvable.", code="return_not_found")
        return ticket

    async def approve(
        self, ticket_id: uuid.UUID, payload: ApproveIn, *, admin_id: uuid.UUID
    ) -> ReturnTicket:
        """Approve the return and issue a refund for the piece."""
        ticket = await self.get(ticket_id)
        self._guard(ticket.status, ReturnStatus.APPROVED)

        amount = payload.amount or await self.repo.line_price(
            ticket.purchase_id, ticket.piece_id
        )
        if amount is None or Decimal(amount) <= 0:
            raise ValidationError(
                "Montant de remboursement introuvable ; précisez-le.",
                code="refund_amount_unknown",
            )

        payment = await self.payments.repo.latest_for_purchase(ticket.purchase_id)
        if payment is None:
            raise ConflictError(
                "Aucun paiement à rembourser pour cette commande.",
                code="no_payment",
            )
        # issue the refund through the payments service (same session -> one commit)
        await self.payments.refund(
            payment.id,
            RefundIn(amount=Decimal(amount), reason=payload.note or "return approved"),
            admin_id=admin_id,
        )

        ticket.status = ReturnStatus.APPROVED
        ticket.resolution_note = payload.note
        await self.db.commit()
        return await self.repo.get(ticket_id)

    async def reject(
        self, ticket_id: uuid.UUID, payload: RejectIn, *, admin_id: uuid.UUID
    ) -> ReturnTicket:
        ticket = await self.get(ticket_id)
        self._guard(ticket.status, ReturnStatus.REJECTED)
        ticket.status = ReturnStatus.REJECTED
        ticket.resolution_note = payload.note
        await self.db.commit()
        return await self.repo.get(ticket_id)

    async def resolve(
        self, ticket_id: uuid.UUID, payload: ResolveIn, *, admin_id: uuid.UUID
    ) -> ReturnTicket:
        """Close an approved return: optionally restock the piece (SOLD ->
        published) once it has been physically received."""
        ticket = await self.get(ticket_id)
        self._guard(ticket.status, ReturnStatus.RESOLVED)
        if payload.restock:
            await self.catalogue.restock(ticket.piece_id)
            ticket.restocked = True
        ticket.status = ReturnStatus.RESOLVED
        if payload.note:
            ticket.resolution_note = payload.note
        await self.db.commit()
        return await self.repo.get(ticket_id)

    # ------------------------------------------------------- helpers
    @staticmethod
    def _guard(current: ReturnStatus, target: ReturnStatus) -> None:
        if target not in _TRANSITIONS[current]:
            raise ConflictError(
                f"Transition de retour invalide : {current.value} → {target.value}.",
                code="invalid_return_transition",
            )