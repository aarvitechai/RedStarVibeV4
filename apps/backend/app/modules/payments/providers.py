"""Payment provider adapters (Razorpay; a sandbox for local/test). The app never depends on a provider SDK directly."""

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, ClassVar, Protocol

import httpx

from app.core.config import get_settings

RAZORPAY_API = "https://api.razorpay.com/v1"
SANDBOX_WEBHOOK_SECRET = "sandbox-webhook-secret"  # noqa: S105 - only used when no real keys and never in staging/production


@dataclass(frozen=True)
class ProviderOrder:
    provider_order_id: str
    public_key: str


class PaymentProvider(Protocol):
    name: str

    async def create_order(self, amount_paise: int, receipt: str, notes: dict[str, str]) -> ProviderOrder: ...
    async def order_paid_payment_id(self, provider_order_id: str) -> str | None: ...
    async def refund(self, provider_payment_id: str, amount_paise: int) -> str: ...
    def verify_webhook(self, body: bytes, signature: str | None) -> bool: ...


class RazorpayProvider:
    name = "razorpay"

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str) -> None:
        self._key_id, self._webhook_secret = key_id, webhook_secret
        self._http = httpx.AsyncClient(base_url=RAZORPAY_API, auth=(key_id, key_secret), timeout=httpx.Timeout(5.0))

    async def _call(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(3):  # bounded retries with backoff for transient errors only
            try:
                r = await self._http.request(method, path, **kw)
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError("provider error", request=r.request, response=r)
                r.raise_for_status()
                data: dict[str, Any] = r.json()
                return data
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
                import asyncio

                await asyncio.sleep(0.3 * 2**attempt + secrets.randbelow(100) / 1000)
        assert last is not None
        raise last

    async def create_order(self, amount_paise: int, receipt: str, notes: dict[str, str]) -> ProviderOrder:
        data = await self._call(
            "POST", "/orders", json={"amount": amount_paise, "currency": "INR", "receipt": receipt[:40], "notes": notes}
        )
        return ProviderOrder(provider_order_id=str(data["id"]), public_key=self._key_id)

    async def order_paid_payment_id(self, provider_order_id: str) -> str | None:
        data = await self._call("GET", f"/orders/{provider_order_id}/payments")
        for p in data.get("items", []):
            if p.get("status") == "captured":
                return str(p["id"])
        return None

    async def refund(self, provider_payment_id: str, amount_paise: int) -> str:
        data = await self._call("POST", f"/payments/{provider_payment_id}/refund", json={"amount": amount_paise})
        return str(data["id"])

    def verify_webhook(self, body: bytes, signature: str | None) -> bool:
        if not signature or not self._webhook_secret:
            return False
        expected = hmac.new(self._webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class SandboxProvider:
    """Local/test stand-in. Orders are fake; 'paying' builds a correctly signed webhook so the real code path runs."""

    name = "sandbox"
    paid: ClassVar[dict[str, str]] = {}  # provider_order_id -> payment id, for reconciliation tests

    async def create_order(self, amount_paise: int, receipt: str, notes: dict[str, str]) -> ProviderOrder:
        return ProviderOrder(provider_order_id=f"sbx_order_{secrets.token_hex(8)}", public_key="sandbox")

    async def order_paid_payment_id(self, provider_order_id: str) -> str | None:
        return self.paid.get(provider_order_id)

    async def refund(self, provider_payment_id: str, amount_paise: int) -> str:
        return f"sbx_rfnd_{secrets.token_hex(6)}"

    def verify_webhook(self, body: bytes, signature: str | None) -> bool:
        expected = hmac.new(SANDBOX_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        return bool(signature) and hmac.compare_digest(expected, signature or "")

    @staticmethod
    def signed_event(event_id: str, provider_order_id: str, payment_id: str, amount_paise: int) -> tuple[bytes, str, str]:
        body = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": payment_id,
                            "order_id": provider_order_id,
                            "amount": amount_paise,
                            "status": "captured",
                            "currency": "INR",
                        }
                    }
                },
            },
            separators=(",", ":"),
        ).encode()
        sig = hmac.new(SANDBOX_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        return body, sig, event_id


@lru_cache(maxsize=1)
def get_provider() -> PaymentProvider:
    s = get_settings()
    if s.razorpay_key_id and s.razorpay_key_secret:
        return RazorpayProvider(s.razorpay_key_id, s.razorpay_key_secret, s.razorpay_webhook_secret)
    if s.is_deployed:
        raise RuntimeError("Razorpay keys are required in staging/production; the sandbox provider is local/test only")
    return SandboxProvider()
