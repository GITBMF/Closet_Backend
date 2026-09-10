"""Order service — checkout and the order lifecycle.

CHECKOUT is the critical path and must be atomic. A ClosET piece is 1-of-1,
so two customers must never both buy it. The service reserves every piece
through catalogue's reserve() contract (an atomic UPDATE ... WHERE
status='published'); if any reservation fails, everything already reserved is
released and checkout is rejected. All DB writes happen in one transaction and
commit once at the end.

The status machine is enforced here — only legal transitions are allowed.
Cancelling releases the reserved pieces; marking paid sells them.

Cross-module calls go through services (catalogue, delivery-pricing), never
their repositories. This service exposes mark_paid()/cancel() for the payments
module to call later.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.catalogue.constants import PieceStatus
from app.modules.catalogue.service import CatalogueService
from app.modules.delivery_pricing.service import DeliveryPricingService
from app.modules.privileges.service import PrivilegeService
from app.modules.identity.constants import ActorType
from app.modules.orders.constants import OrderStatus
from app.modules.orders.models import (
    Purchase,
    PurchaseItem,
    PurchaseStatusHistory,
)
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schemas import CheckoutIn, ManualQuote, StatusUpdate

# legal status transitions (the machine)
_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.QUOTE_REQUIRED: {OrderStatus.PENDING, OrderStatus.CANCELLED},
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
    OrderStatus.READY: {OrderStatus.DELIVERING, OrderStatus.CANCELLED},
    OrderStatus.DELIVERING: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
}

# statuses at which a piece is still only reserved (cancel must release it)
_RESERVED_STATES = {
    OrderStatus.PENDING,
    OrderStatus.QUOTE_REQUIRED,
    OrderStatus.PAID,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.DELIVERING,
}

_RESERVATION_MINUTES = 30


class OrderService:
    def __init__(
        self,
        repo: OrderRepository,
        catalogue: CatalogueService,
        pricing: DeliveryPricingService,
        privileges: PrivilegeService,
    ) -> None:
        self.repo = repo
        self.catalogue = catalogue
        self.pricing = pricing
        self.privileges = privileges

    @property
    def db(self):
        return self.repo.db

    # ------------------------------------------------------- order numbers
    async def _unique_order_number(self) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        for _ in range(20):
            candidate = f"CLO-{stamp}-{secrets.token_hex(2).upper()}"
            if not await self.repo.order_number_exists(candidate):
                return candidate
        raise ConflictError(
            "Impossible de générer un numéro de commande.",
            code="order_number_generation_failed",
        )

    # ============================================================ checkout
    async def checkout(
        self, payload: CheckoutIn, *, user_id: uuid.UUID | None
    ) -> Purchase:
        # de-duplicate piece ids (a 1-of-1 can't be bought twice in one order)
        piece_ids = list(dict.fromkeys(payload.piece_ids))

        # 1. load + validate every piece
        pieces = []
        for pid in piece_ids:
            piece = await self.catalogue.get_piece_for_order(pid)
            if piece is None:
                raise NotFoundError(
                    f"Article {pid} introuvable.", code="piece_not_found"
                )
            if piece.status is not PieceStatus.PUBLISHED:
                raise ConflictError(
                    f"L'article « {piece.title} » n'est plus disponible.",
                    code="piece_unavailable",
                )
            pieces.append(piece)

        order_id = uuid.uuid4()

        # 2. reserve all pieces atomically; roll back reservations on any failure
        reserved: list[uuid.UUID] = []
        for piece in pieces:
            ok = await self.catalogue.reserve(
                piece.id, order_id=order_id, minutes=_RESERVATION_MINUTES
            )
            if not ok:
                # someone grabbed it between validation and reservation
                for done in reserved:
                    await self.catalogue.release(done)
                raise ConflictError(
                    f"L'article « {piece.title} » vient d'être réservé.",
                    code="piece_just_taken",
                )
            reserved.append(piece.id)

        # 3. delivery quote
        quote = await self.pricing.quote(
            city_id=payload.address.city_id, region_id=payload.address.region_id
        )
        delivery_fee = Decimal(quote.amount)
        quote_required = quote.quote_required

        # 4. totals
        subtotal = sum((Decimal(p.price) for p in pieces), Decimal(0))
        discount = Decimal(0)
        applied_code = None
        if payload.privilege_code:
            applied_code, discount = await self.privileges.apply(
                payload.privilege_code, subtotal
            )
        total = subtotal + delivery_fee - discount

        # 5. snapshot + persist (one transaction)
        order_number = await self._unique_order_number()
        status = (
            OrderStatus.QUOTE_REQUIRED if quote_required else OrderStatus.PENDING
        )
        purchase = Purchase(
            id=order_id,
            order_number=order_number,
            user_id=user_id,
            customer_name=payload.customer_name.strip(),
            customer_phone=payload.customer_phone.strip(),
            customer_email=payload.customer_email,
            status=status,
            delivery_address=payload.address.model_dump(),
            delivery_city_id=payload.address.city_id,
            delivery_region_id=payload.address.region_id,
            delivery_fee=delivery_fee,
            subtotal=subtotal,
            discount_amount=discount,
            total=total,
            currency=quote.currency,
            quote_required=quote_required,
            customer_note=payload.customer_note,
            placed_at=datetime.now(UTC),
        )
        await self.repo.add_purchase(purchase)
        if applied_code is not None:
            await self.privileges.redeem(
                applied_code,
                purchase_id=order_id,
                user_id=user_id,
                amount=discount,
            )

        for piece in pieces:
            await self.repo.add_item(
                PurchaseItem(
                    purchase_id=order_id,
                    piece_id=piece.id,
                    title=piece.title,
                    price=Decimal(piece.price),
                )
            )

        await self.repo.add_history(
            PurchaseStatusHistory(
                purchase_id=order_id,
                from_status=None,
                to_status=status,
                actor_type=ActorType.CUSTOMER if user_id else ActorType.SYSTEM,
                actor_id=user_id,
                reason="order placed",
            )
        )

        await self.db.commit()
        return await self.repo.get(order_id, with_items=True)

    # --------------------------------------------------------------- reads
    async def get_by_number(self, order_number: str) -> Purchase:
        order = await self.repo.get_by_number(order_number, with_items=True)
        if order is None:
            raise NotFoundError("Commande introuvable.", code="order_not_found")
        return order

    async def get_for_user(
        self, order_id: uuid.UUID, user_id: uuid.UUID
    ) -> Purchase:
        order = await self.repo.get(order_id, with_items=True)
        if order is None or order.user_id != user_id:
            raise NotFoundError("Commande introuvable.", code="order_not_found")
        return order

    async def get_admin(self, order_id: uuid.UUID) -> Purchase:
        order = await self.repo.get(order_id, with_items=True)
        if order is None:
            raise NotFoundError("Commande introuvable.", code="order_not_found")
        return order

    async def get_history(self, order_id: uuid.UUID) -> list[PurchaseStatusHistory]:
        # 404 if the order doesn't exist, so callers can't probe ids
        if await self.repo.get(order_id) is None:
            raise NotFoundError("Commande introuvable.", code="order_not_found")
        return await self.repo.history_for(order_id)

    async def list_for_user(self, user_id: uuid.UUID, *, limit: int, offset: int):
        return await self.repo.list_for_user(user_id, limit=limit, offset=offset)

    async def list_all(self, *, status: OrderStatus | None, limit: int, offset: int):
        return await self.repo.list_all(status=status, limit=limit, offset=offset)

    # ------------------------------------------------------- status writes
    async def _record_transition(
        self,
        order: Purchase,
        to: OrderStatus,
        *,
        actor_type: ActorType,
        actor_id: uuid.UUID | None,
        reason: str | None,
    ) -> None:
        await self.repo.add_history(
            PurchaseStatusHistory(
                purchase_id=order.id,
                from_status=order.status,
                to_status=to,
                actor_type=actor_type,
                actor_id=actor_id,
                reason=reason,
            )
        )
        order.status = to

    async def update_status(
        self, order_id: uuid.UUID, payload: StatusUpdate, *, admin_id: uuid.UUID
    ) -> Purchase:
        order = await self.repo.get(order_id, with_items=True)
        if order is None:
            raise NotFoundError("Commande introuvable.", code="order_not_found")

        target = payload.status
        if target not in _TRANSITIONS[order.status]:
            raise ConflictError(
                f"Transition invalide: {order.status.value} → {target.value}.",
                code="invalid_transition",
            )

        # cancelling releases any still-reserved pieces
        if target is OrderStatus.CANCELLED and order.status in _RESERVED_STATES:
            for item in order.items:
                await self.catalogue.release(item.piece_id)

        await self._record_transition(
            order, target,
            actor_type=ActorType.ADMIN, actor_id=admin_id, reason=payload.reason,
        )
        await self.db.commit()
        return await self.repo.get(order_id, with_items=True)

    async def set_manual_quote(
        self, order_id: uuid.UUID, payload: ManualQuote, *, admin_id: uuid.UUID
    ) -> Purchase:
        order = await self.repo.get(order_id, with_items=True)
        if order is None:
            raise NotFoundError("Commande introuvable.", code="order_not_found")
        if order.status is not OrderStatus.QUOTE_REQUIRED:
            raise ConflictError(
                "Cette commande n'attend pas de devis.", code="not_quote_required"
            )
        fee = payload.delivery_fee.quantize(Decimal("0.01"))
        order.delivery_fee = fee
        order.total = order.subtotal + fee - order.discount_amount
        order.quote_required = False
        if payload.admin_note:
            order.admin_note = payload.admin_note
        await self._record_transition(
            order, OrderStatus.PENDING,
            actor_type=ActorType.ADMIN, actor_id=admin_id,
            reason="manual delivery quote set",
        )
        await self.db.commit()
        return await self.repo.get(order_id, with_items=True)

    # =======================================================================
    # Cross-module contracts — called by the PAYMENTS module (built later).
    # =======================================================================
    async def mark_paid(self, order_id: uuid.UUID) -> Purchase:
        """Payment confirmed: PENDING -> PAID, and sell every reserved piece."""
        order = await self.repo.get(order_id, with_items=True)
        if order is None:
            raise NotFoundError("Commande introuvable.", code="order_not_found")
        if order.status is not OrderStatus.PENDING:
            raise ConflictError(
                "La commande n'est pas en attente de paiement.",
                code="not_pending",
            )
        for item in order.items:
            await self.catalogue.mark_sold(item.piece_id)
        await self._record_transition(
            order, OrderStatus.PAID,
            actor_type=ActorType.SYSTEM, actor_id=None, reason="payment confirmed",
        )
        await self.db.commit()
        return await self.repo.get(order_id, with_items=True)
    
    
    async def sync_from_delivery(
        self, order_id: uuid.UUID, delivery_status: str
    ) -> None:
        """Advance the order to track delivery progress.

        Called by the delivery module (never the other way round). Delivery owns
        its own status machine; orders owns its own. This maps a delivery status
        onto the order status and applies it through the normal transition
        rules — an illegal jump is simply skipped, so delivery can call this
        idempotently without knowing the order's exact current state.
        """
        mapping = {
            "picked_up": OrderStatus.DELIVERING,
            "in_transit": OrderStatus.DELIVERING,
            "delivered": OrderStatus.COMPLETED,
        }
        target = mapping.get(delivery_status)
        if target is None:
            return
        order = await self.repo.get(order_id, with_items=True)
        if order is None:
            raise NotFoundError("Commande introuvable.", code="order_not_found")
        if order.status is target:
            return
        if target not in _TRANSITIONS[order.status]:
            # e.g. already COMPLETED, or a repeat "in_transit" after DELIVERING —
            # nothing to do; delivery status is the source of truth for itself.
            return
        await self._record_transition(
            order, target,
            actor_type=ActorType.COURIER, actor_id=None,
            reason=f"delivery {delivery_status}",
        )
        # NOTE: caller (delivery service) owns the commit so its delivery write
        # and this order transition land in one transaction.

    async def cancel(
        self, order_id: uuid.UUID, *, reason: str, actor_type: ActorType = ActorType.SYSTEM
    ) -> Purchase:
        """Cancel an order and release any reserved pieces (payment failed/expired)."""
        order = await self.repo.get(order_id, with_items=True)
        if order is None:
            raise NotFoundError("Commande introuvable.", code="order_not_found")
        if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
            raise ConflictError(
                "La commande ne peut plus être annulée.", code="not_cancellable"
            )
        if order.status in _RESERVED_STATES:
            for item in order.items:
                await self.catalogue.release(item.piece_id)
        await self._record_transition(
            order, OrderStatus.CANCELLED,
            actor_type=actor_type, actor_id=None, reason=reason,
        )
        await self.db.commit()
        return await self.repo.get(order_id, with_items=True)