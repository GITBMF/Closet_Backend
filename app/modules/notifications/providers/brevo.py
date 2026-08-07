"""Brevo (ex-Sendinblue) transactional e-mail provider.

Delivers the `email` channel via Brevo's API (POST /v3/smtp/email). Reads all
config through the generic load_email_config() helper — no Brevo-specific
setting names — so switching providers is a config change, not a code change.
Never raises for a delivery problem; returns SendResult the service records.
"""
from __future__ import annotations

import html
import logging

import httpx

from app.modules.notifications.providers.base import ChannelProvider, SendResult
from app.modules.notifications.providers.email_config import load_email_config

logger = logging.getLogger("closet.notifications")


class BrevoProvider(ChannelProvider):
    code = "brevo"
    DEFAULT_BASE_URL = "https://api.brevo.com"

    async def send_message(
        self, *, to: str, subject: str | None, body: str
    ) -> SendResult:
        cfg = load_email_config(self.DEFAULT_BASE_URL)
        if (why := cfg.missing()) is not None:
            return SendResult(ok=False, error=why)

        payload = {
            "sender": {"name": cfg.from_name, "email": cfg.from_address},
            "to": [{"email": to}],
            "subject": subject or "",
            "textContent": body,
            "htmlContent": (
                "<html><body><pre style=\"font:inherit;white-space:pre-wrap;"
                "margin:0\">" + html.escape(body) + "</pre></body></html>"
            ),
        }
        headers = {
            "api-key": cfg.api_key,
            "content-type": "application/json",
            "accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"{cfg.base_url}/v3/smtp/email", json=payload, headers=headers
                )
        except httpx.HTTPError as exc:
            logger.warning("Brevo unreachable: %s", exc)
            return SendResult(ok=False, error=f"Brevo unreachable: {exc}")

        if resp.status_code in (200, 201):
            data = {}
            try:
                data = resp.json() if resp.content else {}
            except ValueError:
                pass
            return SendResult(
                ok=True,
                provider_message_id=str(data.get("messageId", "")) or None,
                raw=data if isinstance(data, dict) else {},
            )

        detail = resp.text[:300] if resp.content else ""
        logger.warning("Brevo send failed: HTTP %s %s", resp.status_code, detail)
        return SendResult(
            ok=False,
            error=f"Brevo HTTP {resp.status_code}: {detail}",
            raw={"status_code": resp.status_code},
        )