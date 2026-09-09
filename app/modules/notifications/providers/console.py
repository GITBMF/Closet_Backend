"""Console (log) provider — the default until real providers are configured.

It "delivers" by logging, and always succeeds. This lets every notify-path in
the app be built and tested now: callers call send(), rows are written, flows
are exercised — without a Twilio/FCM/SMTP account. Swap per channel via config
when credentials arrive; no caller changes.
"""

from __future__ import annotations

import logging

from app.modules.notifications.providers.base import ChannelProvider, SendResult

logger = logging.getLogger("closet.notifications")


class ConsoleProvider(ChannelProvider):
    code = "console"

    async def send_message(
        self, *, to: str, subject: str | None, body: str, html: str | None = None
    ) -> SendResult:
        line = f"[notification] to={to}"
        if subject:
            line += f" subject={subject!r}"
        line += f" body={body!r}"
        if html:
            line += " (+html)"
        logger.info(line)
        return SendResult(ok=True, provider_message_id="console", raw={"logged": True})
