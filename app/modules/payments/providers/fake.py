"""A deterministic, offline payment provider for development and tests.

It never touches the network. It "opens a session" by echoing back a fake URL
and reference, and it fabricates webhook results the test suite can feed to the
service to exercise the success / failure / retry paths. This is what lets the
entire payment flow be built and verified before CinetPay credentials exist.

Not for production: get_provider() will only return this when the active
provider is explicitly "fake".
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

from app.modules.payments.constants import PaymentStatus
from app.modules.payments.providers.base import (
    InitiateRequest,
    InitiateResult,
    RefundResult,
    WebhookResult,
)

# A fixed secret so tests can compute a matching signature deterministically.
_FAKE_SECRET = b"fake-provider-secret"


def _sign(raw_body: bytes) -> str:
    return hmac.new(_FAKE_SECRET, raw_body, hashlib.sha256).hexdigest()


class FakeProvider:
    code = "fake"

    async def initiate(self, req: InitiateRequest) -> InitiateResult:
        ref = f"FAKE-{req.reference}"
        return InitiateResult(
            provider_reference=ref,
            payment_url=f"https://fake-pay.local/checkout/{ref}",
            raw={"reference": req.reference, "amount": str(req.amount)},
        )

    def parse_webhook(
        self, *, raw_body: bytes, headers: dict[str, str]
    ) -> WebhookResult:
        sig = headers.get("x-fake-signature", "")
        valid = hmac.compare_digest(sig, _sign(raw_body))
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return WebhookResult(
                signature_valid=valid, provider_event_id=None,
                provider_reference=None, status=None, event_type=None,
                error="unparseable body",
            )
        status_map = {
            "success": PaymentStatus.SUCCEEDED,
            "failed": PaymentStatus.FAILED,
            "pending": PaymentStatus.PENDING,
        }
        return WebhookResult(
            signature_valid=valid,
            provider_event_id=body.get("event_id"),
            provider_reference=body.get("reference"),
            status=status_map.get(body.get("status")),
            event_type=body.get("status"),
            payload=body,
        )

    async def refund(
        self, *, provider_reference: str, amount: Decimal, reason: str | None
    ) -> RefundResult:
        return RefundResult(
            provider_reference=f"REFUND-{provider_reference}",
            raw={"refunded": str(amount)},
        )

    # helper used by tests to build a correctly-signed webhook
    @staticmethod
    def sign_body(raw_body: bytes) -> str:
        return _sign(raw_body)