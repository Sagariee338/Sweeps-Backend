"""DollarPay transport. Orders are not exposed to players until settlement is wired."""
import ipaddress
import os
from decimal import Decimal
from urllib.parse import urljoin, urlparse

import httpx
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email

from .signing import signature, verify_signature
from ..game_clients.common.validation import https_url


class DollarPayError(Exception):
    pass


class DollarPayUnavailable(DollarPayError):
    pass


class DollarPayRejected(DollarPayError):
    pass


def validate_payin_amount(method, amount_cents):
    allowed = {499, 599, 699, 799, 899, 999, 1099, 1199, 1299, 1399, 1499, 1799, 1999, 2299, 2499, 2999, 3099, 3299, 3999, 4999, 5499, 5999, 9999, 10999, 12499, 12999, 14999, 19999, 24999, 29999, 39999, 49999}
    if (method not in {"1","2","3","4"} or amount_cents not in allowed
            or (method == "4" and amount_cents in {499,599,699,799,899,24999,29999,39999,49999})):
        raise ValueError("Amount is not supported for this pay-in method")


class DollarPayClient:
    def __init__(self, *, http_client=None, base_url=None, merchant_id=None, merchant_key=None):
        self.base_url = (base_url or os.environ.get("DOLLARPAY_API_URL") or "https://mh.dollarpaywallet.com").rstrip("/") + "/"
        self.merchant_id = merchant_id or os.environ.get("DOLLARPAY_MERCHANT_ID", "")
        self.merchant_key = merchant_key or os.environ.get("DOLLARPAY_MERCHANT_KEY", "")
        self.tenant_domain = os.environ.get("DOLLARPAY_TENANT_DOMAIN", "")
        if not self.merchant_id or not self.merchant_key:
            raise DollarPayUnavailable("DollarPay merchant credentials are not configured")
        try:
            https_url(self.base_url, origin_only=True)
        except ValueError as error:
            raise DollarPayUnavailable("DollarPay API URL must be an HTTPS origin") from error
        self.http = http_client if http_client is not None else httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=False)

    def _post(self, path, fields):
        form = {"merchant_id": self.merchant_id, **{key: str(value) for key, value in fields.items()}}
        form["sign"] = signature(form, self.merchant_key)
        headers = {"X-Tenant-Domain": self.tenant_domain} if self.tenant_domain else {}
        try:
            response = self.http.post(urljoin(self.base_url, path.lstrip("/")), data=form, headers=headers)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise DollarPayUnavailable("DollarPay request failed or returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise DollarPayUnavailable("DollarPay response is invalid")
        if str(payload.get("status")) != "00000" and not payload.get("sign"):
            # Some gateway validation errors have no signature. Never treat these as settlement.
            raise DollarPayRejected(str(payload.get("msg") or "DollarPay rejected the request"))
        if not verify_signature(payload, self.merchant_key):
            raise DollarPayUnavailable("DollarPay response signature is invalid")
        if str(payload.get("merchant_id")) != self.merchant_id:
            raise DollarPayUnavailable("DollarPay response merchant does not match")
        if str(payload.get("status")) != "00000":
            raise DollarPayRejected(str(payload.get("msg") or "DollarPay rejected the request"))
        return payload

    def create_payin(self, *, order_sn, user_name, method, amount_cents, notify_url, ip, device_id, return_url=None):
        if method not in {"1", "2", "3", "4"}:
            raise ValueError("Unsupported pay-in method")
        validate_payin_amount(method, amount_cents)
        ipaddress.ip_address(ip)
        if not notify_url.startswith("https://") or (return_url and (not return_url.startswith("https://") or len(return_url) > 128)):
            raise ValueError("Payment callbacks must use HTTPS")
        fields = {
            "order_sn": order_sn, "user_name": user_name, "is_cash": "1", "is_pay": method,
            "amount": f"{Decimal(amount_cents) / 100:.2f}", "notify_url": notify_url,
            "ip": ip, "device_id": device_id,
        }
        if return_url:
            fields["return_url"] = return_url
        payload = self._post("api/payment/pay", fields)
        if payload.get("outer_order_sn") != order_sn:
            raise DollarPayUnavailable("DollarPay order reference does not match")
        return payload

    def query_payin(self, order_sn):
        payload = self._post("api/payment/query", {"outer_order_sn": order_sn})
        if payload.get("outer_order_sn") != order_sn:
            raise DollarPayUnavailable("DollarPay order reference does not match")
        return payload

    def create_payout(self, *, order_sn, method, recipient, amount_cents, notify_url):
        paths = {"cash_app": "api/pay/pay", "paypal": "api/pay/palpalpay", "chime": "api/pay/chimepay"}
        if method not in paths:
            raise ValueError("Unsupported payout method")
        if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
            raise ValueError("Payout amount must be positive integer cents")
        if not recipient or len(recipient) > 120:
            raise ValueError("Invalid payout recipient")
        if method == "paypal":
            try:
                validate_email(recipient)
            except DjangoValidationError as error:
                raise ValueError("PayPal recipient must be an email address") from error
        if not notify_url.startswith("https://"):
            raise ValueError("Payout callback must use HTTPS")
        payload = self._post(paths[method], {
            "order_sn": order_sn, "account_no": recipient,
            "amount": f"{Decimal(amount_cents) / 100:.2f}", "notify_url": notify_url,
        })
        if payload.get("outer_order_sn") != order_sn:
            raise DollarPayUnavailable("DollarPay payout reference does not match")
        return payload

    def query_payout(self, order_sn):
        payload = self._post("api/pay/query", {"outer_order_sn": order_sn})
        if payload.get("outer_order_sn") != order_sn:
            raise DollarPayUnavailable("DollarPay payout reference does not match")
        return payload

    def cancel_payout_order(self, order_sn):
        return self._post("api/pay/cancel_order", {"outer_order_sn": order_sn})

    def balance(self):
        return self._post("api/pay/balance", {})

    def verify_notification(self, payload):
        if not isinstance(payload, dict) or not verify_signature(payload, self.merchant_key):
            raise DollarPayUnavailable("DollarPay notification signature is invalid")
        if str(payload.get("merchant_id")) != self.merchant_id:
            raise DollarPayUnavailable("DollarPay notification merchant does not match")
        return payload
