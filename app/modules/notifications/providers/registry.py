"""Channel -> provider selection.

Reads NOTIFICATIONS_PROVIDERS from settings: a mapping of channel -> provider
code. Any channel not mapped (or mapped to "console") uses the console provider,
so the app always has a working default. Real providers (twilio, fcm, smtp) are
registered here as they're added; none are required to boot.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.modules.notifications.constants import NotificationChannel
from app.modules.notifications.providers.base import ChannelProvider
from app.modules.notifications.providers.console import ConsoleProvider

# As real adapters are written, add them here, e.g. "twilio": TwilioProvider.
_BUILDERS: dict[str, type[ChannelProvider]] = {
    "console": ConsoleProvider,
}


@lru_cache
def get_provider(channel: NotificationChannel) -> ChannelProvider:
    mapping = settings.NOTIFICATIONS_PROVIDERS or {}
    code = mapping.get(channel.value, "console")
    builder = _BUILDERS.get(code, ConsoleProvider)
    return builder()