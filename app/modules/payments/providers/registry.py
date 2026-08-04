"""Provider selection.

get_provider() returns the adapter named by PAYMENTS_ACTIVE_PROVIDER (or an
explicit code). The concrete providers are the only place credentials are read,
so this factory stays trivial and the rest of the app depends on the Protocol.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.modules.payments.providers.base import (
    PaymentProvider,
    PaymentProviderError,
)
from app.modules.payments.providers.cinetpay import CinetPayProvider
from app.modules.payments.providers.fake import FakeProvider

_BUILDERS = {
    "fake": FakeProvider,
    "cinetpay": CinetPayProvider,
}


@lru_cache
def get_provider(code: str | None = None) -> PaymentProvider:
    name = (code or settings.PAYMENTS_ACTIVE_PROVIDER or "fake").lower()
    builder = _BUILDERS.get(name)
    if builder is None:
        raise PaymentProviderError(
            f"Prestataire de paiement inconnu: {name}", code="unknown_provider"
        )
    return builder()