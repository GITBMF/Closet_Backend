"""CinetPay adapter.

Implements the provider interface against CinetPay's checkout API. All
credentials come from settings; NONE are hard-coded. If they're absent the
adapter raises ProviderNotConfigured the moment it's used — so the app boots
without credentials and only a live payment attempt surfaces the gap. That's
what makes "build now, add keys later" safe.

Reference: CinetPay passes an HMAC token in the `x-token` header of its
notification (webhook) calls, computed over the posted fields; we recompute it
with CINETPAY_SECRET and compare. The exact field order is confirmed against
CinetPay's docs at integration time — kept in _expected_signature so there's a
single place to adjust.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from urllib.parse import parse_qs

import httpx

from app.core.config import settings
from app.modules.payments.constants import PaymentStatus
from app.modules.payments.providers.base import (
    InitiateRequest,
    InitiateResult,
    PaymentProviderError,
    ProviderNotConfigured,
    RefundResult,
    WebhookResult,
)

# CinetPay status strings -> our vocabulary
_STATUS_MAP = {
    "ACCEPTED": PaymentStatus.SUCCEEDED,
    "COMPLETED": PaymentStatus.SUCCEEDED,
    "SUCCESS": PaymentStatus.SUCCEEDED,
    "REFUSED": PaymentStatus.FAILED,
    "CANCELED": PaymentStatus.FAILED,
    "FAILED": PaymentStatus.FAILED,
    "PENDING": PaymentStatus.PENDING,
    "WAITING_FOR_CUSTOMER": PaymentStatus.PENDING,
}


class CinetPayProvider:
    code = "cinetpay"

    def __init__(self) -> None:
        self._api_key = settings.CINETPAY_API_KEY
        self._site_id = settings.CINETPAY_SITE_ID
        self._secret = settings.CINETPAY_SECRET
        self._base_url = settings.CINETPAY_BASE_URL.rstrip("/")
        self._notify_url = settings.CINETPAY_NOTIFY_URL

    def _require_config(self) -> None:
        if not (self._api_key and self._site_id and self._secret):
            raise ProviderNotConfigured("cinetpay")

    async def initiate(self, req: InitiateRequest) -> InitiateResult:
        self._require_config()
        # CinetPay expects the amount as an integer in the account currency.
        payload = {
            "apikey": self._api_key,
            "site_id": self._site_id,
            "transaction_id": req.reference,
            "amount": int(req.amount),
            "currency": req.currency,
            "description": req.description,
            "notify_url": req.notify_url or self._notify_url,
            "return_url": req.return_url,
            "customer_name": req.customer_name,
            "customer_phone_number": req.customer_phone,
            "channels": "ALL",
        }
        if req.customer_email:
            payload["customer_email"] = req.customer_email

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(f"{self._base_url}/payment", json=payload)
        except httpx.HTTPError as exc:  # network/timeout
            raise PaymentProviderError(
                f"CinetPay injoignable: {exc}", code="provider_unreachable"
            ) from exc

        data = resp.json() if resp.content else {}
        # CinetPay returns code "201" on success with data.payment_url + token
        if str(data.get("code")) != "201":
            raise PaymentProviderError(
                f"CinetPay a refusé l'initiation: {data.get('message', resp.text)}",
                code="provider_rejected",
            )
        d = data.get("data", {})
        return InitiateResult(
            provider_reference=d.get("payment_token") or req.reference,
            payment_url=d.get("payment_url"),
            raw=data,
        )

    def parse_webhook(
        self, *, raw_body: bytes, headers: dict[str, str]
    ) -> WebhookResult:
        # CinetPay posts form-encoded fields and an x-token HMAC header.
        fields = {k: v[0] for k, v in parse_qs(raw_body.decode("utf-8")).items()}
        token = headers.get("x-token", "")
        valid = self._verify(fields, token)

        status_raw = (fields.get("cpm_result") or fields.get("status") or "").upper()
        # cpm_error_message present + result 00 => accepted, per CinetPay
        if fields.get("cpm_result") == "00":
            status = PaymentStatus.SUCCEEDED
        else:
            status = _STATUS_MAP.get(status_raw, PaymentStatus.PENDING)

        return WebhookResult(
            signature_valid=valid,
            provider_event_id=fields.get("cpm_trans_id"),
            provider_reference=fields.get("cpm_trans_id") or fields.get("transaction_id"),
            status=status,
            event_type=fields.get("cpm_result") or status_raw or None,
            payload=fields,
        )

    def _verify(self, fields: dict[str, str], token: str) -> bool:
        if not self._secret or not token:
            return False
        expected = self._expected_signature(fields)
        return hmac.compare_digest(expected, token)

    def _expected_signature(self, fields: dict[str, str]) -> str:
        # CinetPay concatenates a defined field order, HMAC-SHA256 with the
        # secret key. Kept isolated so the exact recipe is confirmed against the
        # live dashboard in one place at integration time.
        ordered = "".join(
            str(fields.get(k, ""))
            for k in (
                "cpm_site_id", "cpm_trans_id", "cpm_trans_date", "cpm_amount",
                "cpm_currency", "signature", "payment_method", "cel_phone_num",
                "cpm_phone_prefixe", "cpm_language", "cpm_version",
                "cpm_payment_config", "cpm_page_action", "cpm_custom",
                "cpm_designation", "cpm_error_message",
            )
        )
        return hmac.new(
            self._secret.encode("utf-8"), ordered.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    async def refund(
        self, *, provider_reference: str, amount: Decimal, reason: str | None
    ) -> RefundResult:
        self._require_config()
        # Note: mobile-money refunds are frequently manual at the operator level.
        # This calls CinetPay's refund endpoint where supported; callers must be
        # ready for provider_rejected and fall back to a manual reconcile.
        payload = {
            "apikey": self._api_key,
            "site_id": self._site_id,
            "transaction_id": provider_reference,
            "amount": int(amount),
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(f"{self._base_url}/refund", json=payload)
        except httpx.HTTPError as exc:
            raise PaymentProviderError(
                f"CinetPay injoignable: {exc}", code="provider_unreachable"
            ) from exc
        data = resp.json() if resp.content else {}
        if str(data.get("code")) not in {"200", "201"}:
            raise PaymentProviderError(
                f"Remboursement refusé: {data.get('message', resp.text)}",
                code="refund_rejected",
            )
        return RefundResult(provider_reference=provider_reference, raw=data)