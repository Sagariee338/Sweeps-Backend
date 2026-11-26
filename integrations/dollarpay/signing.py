"""DollarPay protocol primitives; no outbound calls are enabled yet."""
import hashlib
from hmac import compare_digest


def signature(fields: dict[str, str], merchant_key: str) -> str:
    if not merchant_key:
        raise ValueError("Merchant key is required")
    if "tenant_domain" in fields or "X-Tenant-Domain" in fields:
        raise ValueError("Tenant domain belongs in a header, not signed form data")
    parts = [f"{key}={value}" for key, value in sorted(fields.items()) if key != "sign"]
    raw = "&".join(parts) + "&key=" + merchant_key
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def verify_signature(fields: dict[str, str], merchant_key: str) -> bool:
    received = fields.get("sign", "")
    try:
        return isinstance(received, str) and bool(received) and compare_digest(signature(fields, merchant_key), received.upper())
    except (ValueError, TypeError):
        return False
