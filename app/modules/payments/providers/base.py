"""Payment provider interface.

Every aggregator (CinetPay now, direct MTN/Orange later) implements this
Protocol. The payment service is written against it, never against a concrete
provider — so switching or adding a provider is a new adapter, not a rewrite,
and the rest of the app is unaffected.

A provider does three things:
  * initiate  — turn an order into a hosted-payment session, returning a URL
                the customer is sent to and a provider reference to track it.
  * parse_webhook — validate a provider callback's signature and translate its
                body into our own vocabulary (succeeded / failed / pending).
  * refund    — return money for a settled payment (may be unsupported).

Nothing here talks to a database. Providers are pure integration adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.modules.payments.constants import PaymentStatus


class PaymentProviderError(Exception):
    """A provider could not fulfil a request (network, config, bad response)."""

    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ProviderNotConfigured(PaymentProviderError):
    """Credentials/settings for this provider are missing.

    Raised lazily, only when the provider is actually used — so the app boots
    fine without credentials and only a real payment attempt surfaces the gap.
    """

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Le prestataire de paiement « {provider} » n'est pas configuré.",
            code="provider_not_configured",
        )


@dataclass(frozen=True)
class InitiateRequest:
    """Everything a provider needs to open a payment session."""

    amount: Decimal
    currency: str
    reference: str          # our idempotency key / order reference
    description: str
    customer_name: str
    customer_phone: str
    customer_email: str | None
    return_url: str
    notify_url: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class InitiateResult:
    """What a provider gives back when a session is opened."""

    provider_reference: str          # the provider's transaction id
    payment_url: str | None          # hosted page to send the customer to
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WebhookResult:
    """A provider callback, normalised into our vocabulary.

    signature_valid is recorded on the event; the service refuses to change any
    payment/order state when it is False.
    """

    signature_valid: bool
    provider_event_id: str | None
    provider_reference: str | None
    status: PaymentStatus | None     # succeeded / failed / pending
    event_type: str | None
    payload: dict = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class RefundResult:
    provider_reference: str | None
    raw: dict = field(default_factory=dict)


@runtime_checkable
class PaymentProvider(Protocol):
    """The contract every payment aggregator adapter implements."""

    code: str

    async def initiate(self, req: InitiateRequest) -> InitiateResult: ...

    def parse_webhook(
        self, *, raw_body: bytes, headers: dict[str, str]
    ) -> WebhookResult: ...

    async def refund(
        self, *, provider_reference: str, amount: Decimal, reason: str | None
    ) -> RefundResult: ...