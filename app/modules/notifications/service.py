"""Notification service — the send() contract every module calls, plus admin
template and branding management.

CONTRACT STABILITY is the whole point of this module (per the work-split doc):
other modules call notifications.send(...) and must never reimplement messaging
or reach a provider directly. So two promises hold no matter what:

  1. send() NEVER raises to the caller for a delivery problem. A failed WhatsApp
     must not roll back an order. Missing template, unresolved recipient, or a
     provider error are all recorded on the notification row (status=failed) and
     send() returns normally. The only thing a caller must do is `await` it.

  2. send() uses its OWN committed transaction for the log row, independent of
     the caller's transaction. It reads the recipient (if user_id given) but does
     not touch the caller's objects. This keeps the caller's unit of work clean.

Rendering is a safe str.format_map with a defaulting dict, so a template
referencing a key the context didn't supply degrades to a visible placeholder
instead of crashing. For e-mail, the brand settings (name, logo, accent colour)
are merged into the context so templates can use {brand_name}/{logo_url}/… and a
branded HTML body can be rendered.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.notifications.constants import (
    NotificationChannel,
    NotificationStatus,
)
from app.modules.notifications.models import (
    Branding,
    Notification,
    NotificationTemplate,
)
from app.modules.notifications.providers.registry import get_provider
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import (
    BrandingUpdate,
    TemplateIn,
    TemplateUpdate,
)

_DEFAULT_LOCALE = "fr"

# Fallbacks used only if the branding singleton hasn't been created yet.
_BRAND_DEFAULTS = {
    "brand_name": "ClosET",
    "logo_url": "",
    "accent_color": "#8A5A2B",
    "support_email": "",
    "footer_note": "",
}


class _SafeDict(dict):
    """Missing keys render as {key} rather than raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render(text_: str, context: dict) -> str:
    return text_.format_map(_SafeDict(context or {}))


class NotificationService:
    def __init__(self, repo: NotificationRepository) -> None:
        self.repo = repo

    @property
    def db(self):
        return self.repo.db

    # ==================================================== THE send() contract
    async def send(
        self,
        code: str,
        *,
        channel: NotificationChannel,
        context: dict | None = None,
        user_id: uuid.UUID | None = None,
        to_email: str | None = None,
        to_phone: str | None = None,
        locale: str = _DEFAULT_LOCALE,
    ) -> Notification:
        """Queue and attempt one notification. Never raises for a delivery
        problem — records the outcome and returns the Notification row.

        Callers pass either a user_id (we resolve the address) or an explicit
        to_email / to_phone (guests). `context` is merged into the template body.
        """
        context = context or {}

        # resolve recipient address (best effort; failures are recorded, not raised)
        email, phone = to_email, to_phone
        if user_id is not None and (email is None and phone is None):
            email, phone = await self._resolve_user_contact(user_id)

        notification = Notification(
            recipient_user_id=user_id,
            recipient_email=email,
            recipient_phone=phone,
            channel=channel,
            template_code=code,
            payload=context,
            status=NotificationStatus.QUEUED,
        )
        await self.repo.add_notification(notification)

        # --- everything below records outcome on the row; no raising ---
        try:
            template = await self.repo.get_template_with_fallback(
                code, channel, locale, _DEFAULT_LOCALE
            )
            if template is None:
                return await self._fail(
                    notification, f"no template for ({code}, {channel.value})"
                )

            to = self._address_for(channel, email, phone)
            if to is None:
                return await self._fail(
                    notification, f"no {channel.value} address for recipient"
                )

            # e-mail gets the brand settings merged in, so templates can use
            # {brand_name}/{logo_url}/{accent_color}/… and render branded HTML.
            render_ctx = context
            html: str | None = None
            if channel is NotificationChannel.EMAIL:
                render_ctx = {**(await self._branding_context()), **context}

            subject = _render(template.subject, render_ctx) if template.subject else None
            body = _render(template.body, render_ctx)
            if channel is NotificationChannel.EMAIL and template.html_body:
                html = _render(template.html_body, render_ctx)

            provider = get_provider(channel)
            result = await provider.send_message(
                to=to, subject=subject, body=body, html=html
            )

            if result.ok:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(UTC)
            else:
                notification.status = NotificationStatus.FAILED
                notification.error_message = result.error or "provider reported failure"
            await self.db.commit()
            return notification
        except Exception as exc:  # noqa: BLE001 — send() must never propagate
            return await self._fail(notification, f"unexpected: {exc!s}")

    async def _fail(self, notification: Notification, message: str) -> Notification:
        notification.status = NotificationStatus.FAILED
        notification.error_message = message
        await self.db.commit()
        return notification

    @staticmethod
    def _address_for(
        channel: NotificationChannel, email: str | None, phone: str | None
    ) -> str | None:
        if channel is NotificationChannel.EMAIL:
            return email
        if channel in (NotificationChannel.SMS, NotificationChannel.WHATSAPP):
            return phone
        if channel is NotificationChannel.PUSH:
            # push resolves device tokens at the provider; use the user's phone
            # as a routing hint for now (console provider just logs it).
            return phone or email
        return None

    async def _resolve_user_contact(
        self, user_id: uuid.UUID
    ) -> tuple[str | None, str | None]:
        """Load a user's email/phone without importing identity's repository —
        a light direct read keeps the module boundary clean."""
        from sqlalchemy import select

        from app.modules.identity.models import User

        user = (
            await self.db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            return None, None
        return user.email, user.phone

    async def _branding_context(self) -> dict:
        """Brand values for e-mail rendering. Read-only during send() (the row is
        ensured at startup); falls back to defaults if it's somehow missing."""
        b = await self.repo.get_branding()
        if b is None:
            return dict(_BRAND_DEFAULTS)
        return {
            "brand_name": b.brand_name or _BRAND_DEFAULTS["brand_name"],
            "logo_url": b.logo_url or "",
            "accent_color": b.accent_color or _BRAND_DEFAULTS["accent_color"],
            "support_email": b.support_email or "",
            "footer_note": b.footer_note or "",
        }

    # ==================================================== admin: templates
    async def create_template(self, payload: TemplateIn) -> NotificationTemplate:
        existing = await self.repo.get_template(
            payload.code, payload.channel, payload.locale
        )
        if existing is not None:
            raise ConflictError(
                "Un modèle existe déjà pour ce (code, canal, langue).",
                code="template_exists",
            )
        template = NotificationTemplate(
            code=payload.code, channel=payload.channel, locale=payload.locale,
            subject=payload.subject, body=payload.body, html_body=payload.html_body,
        )
        await self.repo.add_template(template)
        await self.db.commit()
        return template

    async def update_template(
        self, template_id: int, payload: TemplateUpdate
    ) -> NotificationTemplate:
        template = await self.repo.get_template_by_id(template_id)
        if template is None:
            raise NotFoundError("Modèle introuvable.", code="template_not_found")
        fields = payload.model_dump(exclude_unset=True)
        if "subject" in fields:
            template.subject = fields["subject"]
        if "body" in fields and fields["body"] is not None:
            template.body = fields["body"]
        if "html_body" in fields:
            # "" clears the HTML (falls back to plain body); a string sets it.
            template.html_body = fields["html_body"] or None
        await self.db.commit()
        return template

    async def list_templates(self, *, code=None, channel=None):
        return await self.repo.list_templates(code=code, channel=channel)

    # ==================================================== admin: branding
    async def get_branding(self) -> Branding:
        """Return the branding singleton, creating it with defaults if absent."""
        b = await self.repo.get_branding()
        if b is None:
            b = Branding(
                id=1,
                brand_name=_BRAND_DEFAULTS["brand_name"],
                accent_color=_BRAND_DEFAULTS["accent_color"],
            )
            self.repo.add_branding(b)
            await self.db.commit()
            b = await self.repo.get_branding()
        return b

    async def update_branding(self, payload: BrandingUpdate) -> Branding:
        b = await self.get_branding()
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(b, key, value)
        b.updated_at = datetime.now(UTC)
        await self.db.commit()
        return b

    # ==================================================== admin: dispatch log
    async def list_notifications(self, *, status=None, channel=None, user_id=None,
                                 limit=20, offset=0):
        return await self.repo.list_notifications(
            status=status, channel=channel, user_id=user_id,
            limit=limit, offset=offset,
        )
