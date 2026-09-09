"""Resend transactional e-mail provider.

Alternative to Brevo. Reads the SAME generic settings via load_email_config()
(EMAIL_API_KEY / EMAIL_FROM_ADDRESS / …), so switching from Brevo to Resend is
just: NOTIFICATIONS_PROVIDERS={"email":"resend"} + set EMAIL_API_KEY to your
Resend key. No other changes.

Resend API: POST /emails, Bearer auth, JSON {from,to,subject,text,html}.
When the template supplies rich `html`, it is sent as-is; otherwise the
plain-text `body` is wrapped in a <pre> so it still renders.
"""
from __future__ import annotations

import html as html_lib
import logging

import httpx

from app.modules.notifications.providers.base import ChannelProvider, SendResult
from app.modules.notifications.providers.email_config import load_email_config

logger = logging.getLogger("closet.notifications")


def _fallback_html(body: str) -> str:
    return (
        '<pre style="font:inherit;white-space:pre-wrap;margin:0">'
        + html_lib.escape(body) + "</pre>"
    )


class ResendProvider(ChannelProvider):
    code = "resend"
    DEFAULT_BASE_URL = "https://api.resend.com"

    async def send_message(
        self, *, to: str, subject: str | None, body: str, html: str | None = None
    ) -> SendResult:
        cfg = load_email_config(self.DEFAULT_BASE_URL)
        if (why := cfg.missing()) is not None:
            return SendResult(ok=False, error=why)

        # Resend wants a "Name <email>" from-string.
        sender = f"{cfg.from_name} <{cfg.from_address}>" if cfg.from_name else cfg.from_address
        payload = {
            "from": sender,
            "to": [to],
            "subject": subject or "",
            "text": body,
            "html": html if html else _fallback_html(body),
        }
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"{cfg.base_url}/emails", json=payload, headers=headers
                )
        except httpx.HTTPError as exc:
            logger.warning("Resend unreachable: %s", exc)
            return SendResult(ok=False, error=f"Resend unreachable: {exc}")

        if resp.status_code in (200, 201):
            data = {}
            try:
                data = resp.json() if resp.content else {}
            except ValueError:
                pass
            return SendResult(
                ok=True,
                provider_message_id=str(data.get("id", "")) or None,
                raw=data if isinstance(data, dict) else {},
            )

        detail = resp.text[:300] if resp.content else ""
        logger.warning("Resend send failed: HTTP %s %s", resp.status_code, detail)
        return SendResult(
            ok=False,
            error=f"Resend HTTP {resp.status_code}: {detail}",
            raw={"status_code": resp.status_code},
        )
