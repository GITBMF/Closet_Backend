"""Channel -> provider selection.

Reads NOTIFICATIONS_PROVIDERS from settings: a mapping of channel -> provider
code. Any channel not mapped (or mapped to "console") uses the console provider,
so the app always has a working default. Real providers (twilio, fcm, smtp) are
registered here as they're added; none are required to boot.
"""

from __future__ import annotations

import json
from functools import lru_cache

from app.core.config import settings
from app.modules.notifications.constants import NotificationChannel
from app.modules.notifications.providers.base import ChannelProvider
from app.modules.notifications.providers.brevo import BrevoProvider
from app.modules.notifications.providers.console import ConsoleProvider
from app.modules.notifications.providers.resend import ResendProvider

# As real adapters are written, add them here, e.g. "twilio": TwilioProvider.
_BUILDERS: dict[str, type[ChannelProvider]] = {
    "console": ConsoleProvider,
    "brevo": BrevoProvider,
    "resend": ResendProvider,
}


def _provider_mapping() -> dict[str, str]:
    """Normalise the configured mapping.

    NOTIFICATIONS_PROVIDERS may arrive as a dict (Python default) or as a JSON
    string (when supplied via an environment variable). Accept both, and fall
    back to an empty mapping on anything unparseable — a bad config value must
    never break sending; it just means "use the console default".
    """
    raw = settings.NOTIFICATIONS_PROVIDERS
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass
    return {}


@lru_cache
def get_provider(channel: NotificationChannel) -> ChannelProvider:
    code = _provider_mapping().get(channel.value, "console")
    builder = _BUILDERS.get(code, ConsoleProvider)
    return builder()