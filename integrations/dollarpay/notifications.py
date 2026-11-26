"""Signed DollarPay notification journal; no monetary ledger postings occur here."""
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .signing import verify_signature
from ..models import DollarPayNotification, DollarPayOrder


class NotificationError(Exception):
    pass


class InvalidNotification(NotificationError):
    pass


class UnknownOrder(NotificationError):
    pass


@dataclass(frozen=True)
class NotificationOutcome:
    order_id: str
    state: str
    duplicate: bool


def _amount_cents(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    try:
        dollars = Decimal(str(value))
    except InvalidOperation:
        return None
    if not dollars.is_finite():
        return None
    cents = dollars * 100
    if dollars <= 0 or cents != cents.to_integral_value() or cents > 2_147_483_647:
        return None
    return int(cents)


def _payload_digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@transaction.atomic
def record_dollarpay_notification(payload, *, merchant_id, merchant_key):
    """Validate and record a gateway event once; financial settlement is a later gated step."""
    if not isinstance(payload, dict) or len(payload) > 40 or any(
        not isinstance(key, str) or not isinstance(value, (str, int)) or isinstance(value, bool)
        for key, value in payload.items()
    ):
        raise InvalidNotification("Invalid notification fields")
    if str(payload.get("merchant_id")) != merchant_id or not verify_signature(payload, merchant_key):
        raise InvalidNotification("Invalid merchant or signature")
    order_sn = str(payload.get("outer_order_sn", ""))
    if not order_sn or len(order_sn) > 120:
        raise InvalidNotification("Invalid order reference")
    order = DollarPayOrder.objects.select_for_update().filter(merchant_order_sn=order_sn).first()
    if not order or order.merchant_id != merchant_id:
        raise UnknownOrder("Order is not registered")
    digest = _payload_digest(payload)
    if DollarPayNotification.objects.filter(payload_sha256=digest).exists():
        return NotificationOutcome(str(order.id), order.state, True)

    pay_status = str(payload.get("pay_status", ""))
    gateway_status = str(payload.get("status", ""))
    amount = _amount_cents(payload.get("primary_amount", payload.get("amount")))
    provider_tx_id = str(payload.get("transaction_id", ""))[:120]
    reason = ""
    next_state = order.state

    if amount != order.amount_cents:
        reason = "Notification amount mismatch"
    elif gateway_status != "00000":
        reason = "Gateway status requires review"
    elif order.provider_transaction_id and provider_tx_id and order.provider_transaction_id != provider_tx_id:
        reason = "Provider transaction reference changed"
    elif pay_status == "0" and order.state == DollarPayOrder.State.PENDING:
        pass
    elif pay_status == "1" and order.state in {DollarPayOrder.State.PENDING, DollarPayOrder.State.SUCCEEDED}:
        next_state = DollarPayOrder.State.SUCCEEDED
    elif pay_status == "5" and order.state in {DollarPayOrder.State.PENDING, DollarPayOrder.State.FAILED}:
        next_state = DollarPayOrder.State.FAILED
    elif pay_status == "4" and order.kind == DollarPayOrder.Kind.PAYIN and order.state in {
        DollarPayOrder.State.SUCCEEDED, DollarPayOrder.State.REFUNDED,
    }:
        next_state = DollarPayOrder.State.REFUNDED
    else:
        reason = "Unexpected notification transition"

    if reason:
        next_state = DollarPayOrder.State.REVIEW
        order.review_reason = reason
    if provider_tx_id and not order.provider_transaction_id:
        order.provider_transaction_id = provider_tx_id
    order.state = next_state
    order.save(update_fields=["state", "review_reason", "provider_transaction_id", "updated_at"])
    DollarPayNotification.objects.create(
        order=order, payload_sha256=digest, pay_status=pay_status[:10], gateway_status=gateway_status[:20],
        amount_cents=amount, provider_transaction_id=provider_tx_id, recorded_state=next_state,
    )
    return NotificationOutcome(str(order.id), next_state, False)
