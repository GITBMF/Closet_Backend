"""Delivery service — courier assignment, the signed courier link, and status.

Two things to know:

  * ORDER OWNERSHIP. When a courier moves a delivery forward, the order must
    follow (READY -> DELIVERING -> COMPLETED). Delivery never writes the order's
    tables; it calls OrderService.sync_from_delivery() and lets orders apply its
    own rules. The delivery write and the order transition share one commit.

  * COURIER LINK (spec 7.3). A courier usually has no account. The admin mints a
    signed, expiring, limited-use link; the RAW token is returned once and only
    its sha256 hash is stored. Every courier call carries the raw token in the
    URL — we hash it, look up the link, and check expiry / revoked / use-count
    before trusting it. The token IS the authentication.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core import security
from app.core.exceptions import (
    PermissionDeniedError,
    ConflictError,
    NotFoundError,
)
from app.modules.delivery.constants import (
    DELIVERY_TRANSITIONS,
    SOURCE_ADMIN,
    SOURCE_COURIER,
    DeliveryStatus,
)
from app.modules.delivery.models import (
    Courier,
    CourierAccessLink,
    Delivery,
    DeliveryEvent,
)
from app.modules.delivery.repository import DeliveryRepository
from app.modules.delivery.schemas import (
    AdminStatusIn,
    AssignIn,
    CourierDeliveryView,
    CourierIn,
    CourierStatusIn,
    CreateDeliveryIn,
    LinkIn,
)
from app.modules.orders.constants import OrderStatus
from app.modules.notifications.constants import NotificationChannel
from app.modules.notifications.hook import Notifier, send_notification
from app.modules.orders.service import OrderService

# delivery statuses that count as "the courier has the parcel in hand"
_PICKED = {DeliveryStatus.PICKED_UP, DeliveryStatus.IN_TRANSIT}


class DeliveryService:
    def __init__(
        self, repo: DeliveryRepository, orders: OrderService,
        notifier: Notifier = send_notification,
    ) -> None:
        self.repo = repo
        self.orders = orders
        self._notify = notifier

    async def _safe_notify(self, *args, **kwargs) -> None:
        """Never let a notifier failure break a delivery flow."""
        try:
            await self._notify(*args, **kwargs)
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger("closet.delivery").warning(
                "notification suppressed during delivery flow", exc_info=True
            )

    @property
    def db(self):
        return self.repo.db

    # =============================================================== couriers
    async def create_courier(self, payload: CourierIn) -> Courier:
        courier = Courier(full_name=payload.full_name, phone=payload.phone)
        await self.repo.add_courier(courier)
        await self.db.commit()
        return courier

    async def list_couriers(self, *, active_only: bool = False) -> list[Courier]:
        return await self.repo.list_couriers(active_only=active_only)

    # ============================================================= deliveries
    async def create_delivery(self, payload: CreateDeliveryIn) -> Delivery:
        """Create the delivery for a READY order, optionally assigning a courier."""
        order = await self.orders.get_by_number(payload.order_number)

        if order.status is not OrderStatus.READY:
            raise ConflictError(
                "La commande doit être prête (READY) avant la création d'une livraison.",
                code="order_not_ready",
            )
        if await self.repo.get_for_purchase(order.id) is not None:
            raise ConflictError(
                "Une livraison existe déjà pour cette commande.",
                code="delivery_exists",
            )

        courier_id = None
        if payload.courier_id is not None:
            courier = await self.repo.get_courier(payload.courier_id)
            if courier is None or not courier.is_active:
                raise NotFoundError("Coursier introuvable ou inactif.", code="courier_not_found")
            courier_id = courier.id

        delivery = Delivery(
            purchase_id=order.id,
            courier_id=courier_id,
            status=DeliveryStatus.ASSIGNED,
        )
        await self.repo.add_delivery(delivery)
        await self.repo.add_event(
            DeliveryEvent(
                delivery_id=delivery.id, status=DeliveryStatus.ASSIGNED,
                source=SOURCE_ADMIN, reason="delivery created",
            )
        )
        await self.db.commit()
        return await self.repo.get(delivery.id)

    async def assign(self, delivery_id: uuid.UUID, payload: AssignIn) -> Delivery:
        delivery = await self._require(delivery_id)
        courier = await self.repo.get_courier(payload.courier_id)
        if courier is None or not courier.is_active:
            raise NotFoundError("Coursier introuvable ou inactif.", code="courier_not_found")
        delivery.courier_id = courier.id
        # reassigning a failed delivery revives it
        if delivery.status is DeliveryStatus.FAILED:
            delivery.status = DeliveryStatus.ASSIGNED
            await self.repo.add_event(
                DeliveryEvent(
                    delivery_id=delivery.id, status=DeliveryStatus.ASSIGNED,
                    source=SOURCE_ADMIN, reason="reassigned after failure",
                )
            )
        await self.db.commit()
        return await self.repo.get(delivery.id)

    async def get(self, delivery_id: uuid.UUID) -> Delivery:
        return await self._require(delivery_id)

    async def list_all(self, *, status, limit, offset):
        return await self.repo.list_all(status=status, limit=limit, offset=offset)

    async def events(self, delivery_id: uuid.UUID):
        await self._require(delivery_id)
        return await self.repo.events_for(delivery_id)

    # ------------------------------------------------ admin status override
    async def admin_update_status(
        self, delivery_id: uuid.UUID, payload: AdminStatusIn, *, admin_id: uuid.UUID
    ) -> Delivery:
        delivery = await self._require(delivery_id)
        await self._apply_status(
            delivery, payload.status, source=SOURCE_ADMIN, reason=payload.reason
        )
        await self.db.commit()
        return await self.repo.get(delivery.id)

    # ================================================== courier links (7.3)
    async def generate_link(
        self, delivery_id: uuid.UUID, payload: LinkIn
    ) -> tuple[CourierAccessLink, str]:
        """Mint a signed, expiring link. Returns (link, RAW token).

        The raw token is shown to the admin exactly once here; only its hash is
        stored. Hand it to the courier (SMS/WhatsApp) as /courier/<token>.
        """
        delivery = await self._require(delivery_id)
        raw = security.generate_opaque_token()
        link = CourierAccessLink(
            delivery_id=delivery.id,
            token_hash=security.hash_opaque_token(raw),
            expires_at=datetime.now(UTC) + timedelta(hours=payload.ttl_hours),
            max_uses=payload.max_uses,
        )
        await self.repo.add_link(link)
        await self.db.commit()
        refreshed = await self.repo.get_link_by_hash(link.token_hash)
        return refreshed, raw

    async def _resolve_link(self, raw_token: str) -> CourierAccessLink:
        """Validate a raw courier token: hash -> lookup -> expiry/revoke/uses."""
        link = await self.repo.get_link_by_hash(security.hash_opaque_token(raw_token))
        if link is None:
            raise PermissionDeniedError("Lien invalide.", code="invalid_link")
        now = datetime.now(UTC)
        if link.revoked_at is not None:
            raise PermissionDeniedError("Lien révoqué.", code="link_revoked")
        if link.expires_at <= now:
            raise PermissionDeniedError("Lien expiré.", code="link_expired")
        if link.used >= link.max_uses:
            raise PermissionDeniedError("Lien épuisé.", code="link_exhausted")
        return link

    async def courier_view(self, raw_token: str) -> CourierDeliveryView:
        link = await self._resolve_link(raw_token)
        return await self._view_for_delivery(link.delivery_id)

    async def _view_for_delivery(self, delivery_id: uuid.UUID) -> CourierDeliveryView:
        delivery, purchase = await self.repo.get_delivery_with_purchase(delivery_id)
        if delivery is None:
            raise NotFoundError("Livraison introuvable.", code="delivery_not_found")
        return CourierDeliveryView(
            order_number=purchase.order_number,
            status=delivery.status,
            customer_name=purchase.customer_name,
            customer_phone=purchase.customer_phone,
            delivery_address=purchase.delivery_address,
            items_count=await self.repo.count_items(purchase.id),
        )

    async def courier_update_status(
        self, raw_token: str, payload: CourierStatusIn
    ) -> CourierDeliveryView:
        link = await self._resolve_link(raw_token)
        delivery = await self.repo.get(link.delivery_id)
        if delivery is None:
            raise NotFoundError("Livraison introuvable.", code="delivery_not_found")

        await self._apply_status(
            delivery, payload.status, source=SOURCE_COURIER,
            reason=payload.reason, link_id=link.id,
        )
        # count the use (this call may consume the last allowed use — that's fine,
        # we build the response from the delivery we already hold, not by
        # re-resolving the now-possibly-exhausted link)
        link.used += 1
        await self.db.commit()
        return await self._view_for_delivery(delivery.id)

    # ------------------------------------------------------------- internals
    async def _apply_status(
        self, delivery: Delivery, target: DeliveryStatus, *,
        source: str, reason: str | None, link_id: uuid.UUID | None = None,
    ) -> None:
        """Move a delivery through its own state machine and mirror to the order.

        Does NOT commit — the caller owns the transaction so the delivery write
        and the order transition are atomic.
        """
        if target is delivery.status:
            return
        if target not in DELIVERY_TRANSITIONS[delivery.status]:
            raise ConflictError(
                f"Transition de livraison invalide: {delivery.status.value} → {target.value}.",
                code="invalid_delivery_transition",
            )

        now = datetime.now(UTC)
        if target in _PICKED and delivery.picked_up_at is None:
            delivery.picked_up_at = now
        if target is DeliveryStatus.DELIVERED:
            delivery.delivered_at = now
        if target is DeliveryStatus.FAILED and reason:
            delivery.failure_reason = reason

        delivery.status = target
        await self.repo.add_event(
            DeliveryEvent(
                delivery_id=delivery.id, status=target,
                source=source, reason=reason, link_id=link_id,
            )
        )
        # mirror onto the order (orders applies its own rules; illegal -> no-op)
        await self.orders.sync_from_delivery(delivery.purchase_id, target.value)

        # tell the customer on the meaningful transitions (own session, never raises)
        _CUSTOMER_MSG = {
            DeliveryStatus.PICKED_UP: "order.delivering",
            DeliveryStatus.DELIVERED: "order.delivered",
        }
        code = _CUSTOMER_MSG.get(target)
        if code is not None:
            _, purchase = await self.repo.get_delivery_with_purchase(delivery.id)
            if purchase is not None:
                await self._safe_notify(
                    code,
                    channel=NotificationChannel.WHATSAPP,
                    to_phone=purchase.customer_phone,
                    context={
                        "customer_name": purchase.customer_name,
                        "order_number": purchase.order_number,
                    },
                )

    async def _require(self, delivery_id: uuid.UUID) -> Delivery:
        delivery = await self.repo.get(delivery_id)
        if delivery is None:
            raise NotFoundError("Livraison introuvable.", code="delivery_not_found")
        return delivery