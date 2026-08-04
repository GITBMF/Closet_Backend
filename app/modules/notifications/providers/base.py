"""Channel provider interface.

Each channel (WhatsApp, SMS, email, push) is delivered by a provider that
implements this Protocol. The notification service is written against the
Protocol, never a concrete provider — so swapping in Twilio / FCM / an SMTP
service later is a new adapter behind config, not a change to any caller.

A provider does exactly one thing: given a rendered message and a resolved
recipient address, try to deliver it and report success/failure. It never
touches the database and never raises for a normal delivery failure — it returns
a SendResult the service records.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)


class ChannelProvider:
    """Base class every channel adapter subclasses. `code` names the channel."""

    code: str = "base"

    async def send_message(
        self, *, to: str, subject: str | None, body: str
    ) -> SendResult:
        raise NotImplementedError