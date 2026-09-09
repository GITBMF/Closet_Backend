"""Provider-agnostic e-mail configuration.

Every e-mail adapter (Brevo, Resend, …) reads its credentials and sender
identity through this ONE helper, using GENERIC setting names. Switching
providers is therefore a config change, never a code change and never a rename:

    # .env — use Brevo
    NOTIFICATIONS_PROVIDERS={"email":"brevo"}
    EMAIL_API_KEY=xkeysib-...

    # .env — switch to Resend later: change two values, nothing else
    NOTIFICATIONS_PROVIDERS={"email":"resend"}
    EMAIL_API_KEY=re_...

Generic settings (app/core/config.py):
    EMAIL_FROM_ADDRESS   the sender address (must be verified at the provider)
    EMAIL_FROM_NAME      sender display name (default "ClosET")
    EMAIL_API_KEY        API key for whichever provider is selected
    EMAIL_API_BASE_URL   optional override of the provider's API base URL
                         (leave empty in production; each adapter supplies its
                         own default — useful only for tests / self-hosting)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class EmailConfig:
    api_key: str
    from_address: str
    from_name: str
    base_url: str          # already resolved: override if set, else provider default

    @property
    def is_configured(self) -> bool:
        """True only when we have both an API key and a verified sender."""
        return bool(self.api_key and self.from_address)

    def missing(self) -> str | None:
        """A human-readable reason we can't send yet, or None if we can."""
        if not self.api_key:
            return "EMAIL_API_KEY is not set."
        if not self.from_address:
            return "EMAIL_FROM_ADDRESS is not set (provider needs a verified sender)."
        return None


def load_email_config(default_base_url: str) -> EmailConfig:
    """Read the generic e-mail settings. `default_base_url` is the calling
    provider's own API base, used when EMAIL_API_BASE_URL is not overridden."""
    override = (getattr(settings, "EMAIL_API_BASE_URL", "") or "").strip()
    return EmailConfig(
        api_key=(getattr(settings, "EMAIL_API_KEY", "") or "").strip(),
        from_address=(getattr(settings, "EMAIL_FROM_ADDRESS", "") or "").strip(),
        from_name=(getattr(settings, "EMAIL_FROM_NAME", "") or "ClosET").strip(),
        base_url=(override or default_base_url).rstrip("/"),
    )