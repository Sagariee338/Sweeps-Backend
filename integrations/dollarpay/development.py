"""Signed DollarPay development flow, with a network-free gateway and TST ledger.

Real merchant credentials are never read here. Test credits cannot enter USD
wallets or real game accounts. A checkout redirect never settles a payment.
"""

from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qsl

import httpx
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from identity.models import PlayControl
from identity.services import apply_pending_limit
from wallet.models import LedgerAccount, LedgerEntry
from wallet.services import account_balance_cents, post_transaction
from integrations.models import DevPaymentOrder, DevGatewayOrder, DevPaymentEvent
from .client import (
    DollarPayClient,
    DollarPayError,
    DollarPayRejected,
    validate_payin_amount,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from .notifications import _amount_cents, _payload_digest
from .signing import signature, verify_signature

MERCHANT = "development-only"
KEY = "local-signed-callback-simulator-not-a-live-merchant-key"
CURRENCY = "TST"
PAYIN_METHODS = {"cash_app": "1", "apple_pay": "2", "google_pay": "3", "card": "4"}


def enabled():
    return bool(settings.DEBUG and settings.DOLLARPAY_DEV_MODE)


def require_dev():
    if not enabled():
        raise NotFound()


def accounts(user):
    return {
        kind: LedgerAccount.objects.get_or_create(
            owner=user, kind=kind, currency=CURRENCY
        )[0]
        for kind in ["player_available", "player_held", "payment_clearing"]
    }


def wallet(user):
    a = accounts(user)
    return {
        "currency": CURRENCY,
        "available_cents": account_balance_cents(a["player_available"]),
        "held_cents": account_balance_cents(a["player_held"]),
    }


def data(order):
    return {
        "id": str(order.id),
        "kind": order.kind,
        "method": order.method,
        "amount_cents": order.amount_cents,
        "currency": CURRENCY,
        "state": order.state,
        "checkout_path": f"/wallet/checkout/{order.id}"
        if order.kind == "payin"
        else None,
        "review_reason": order.review_reason,
        "created_at": order.created_at,
    }


def _signed(fields):
    return {**fields, "sign": signature(fields, KEY)}


def _reply(order, gateway):
    return _signed(
        {
            "merchant_id": MERCHANT,
            "status": "00000",
            "outer_order_sn": order.id.hex,
            "transaction_id": gateway.transaction_id,
            "pay_status": gateway.pay_status,
            "primary_amount": f"{Decimal(order.amount_cents) / 100:.2f}",
            "pay_url": f"https://dev.dollarpay.invalid/checkout/{order.id}",
        }
    )


def transport(request):
    require_dev()
    if request.url.host != "dev.dollarpay.invalid":
        raise RuntimeError("Development transport cannot use a real payment host")
    fields = dict(parse_qsl(request.content.decode(), keep_blank_values=True))
    if fields.get("merchant_id") != MERCHANT or not verify_signature(fields, KEY):
        return httpx.Response(
            200, json={"status": "90001", "msg": "Invalid development signature"}
        )
    reference = fields.get("order_sn") or fields.get("outer_order_sn")
    try:
        order = DevPaymentOrder.objects.get(pk=reference)
    except (
        DevPaymentOrder.DoesNotExist,
        ValueError,
        ValidationError,
        DjangoValidationError,
    ):
        return httpx.Response(
            200, json={"status": "90004", "msg": "Unknown development order"}
        )
    path = request.url.path
    expected_kind = "payin" if path.startswith("/api/payment/") else "payout"
    if order.kind != expected_kind:
        return httpx.Response(
            200, json={"status": "90004", "msg": "Order type mismatch"}
        )
    if path.endswith("/query"):
        gateway = DevGatewayOrder.objects.filter(order=order).first()
        if not gateway:
            return httpx.Response(
                200, json={"status": "90004", "msg": "Order not submitted"}
            )
    else:
        if _amount_cents(fields.get("amount")) != order.amount_cents:
            return httpx.Response(
                200, json={"status": "90003", "msg": "Amount mismatch"}
            )
        gateway, _ = DevGatewayOrder.objects.get_or_create(
            order=order, defaults={"transaction_id": f"dev-{order.id.hex}"}
        )
    return httpx.Response(200, json=_reply(order, gateway))


def client():
    require_dev()
    value = DollarPayClient(
        base_url="https://dev.dollarpay.invalid",
        merchant_id=MERCHANT,
        merchant_key=KEY,
        http_client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    value.tenant_domain = ""
    return value


def _require_deposit_allowed(user, amount_cents):
    """Caller holds the owner row lock, shared with limit updates/settlement."""
    control = PlayControl.objects.select_for_update().filter(user=user).first()
    if control is None:
        return
    apply_pending_limit(control)
    if control.excluded_until and control.excluded_until > timezone.now():
        raise ValidationError("Test deposits are paused for this account")
    limit = control.daily_funding_limit_cents
    if limit is None:
        return
    # Settled deposits consume gross allowance for 24 hours, including refunds.
    paid = (
        LedgerEntry.objects.filter(
            account__owner=user,
            account__currency=CURRENCY,
            account__kind=LedgerAccount.Kind.PLAYER_AVAILABLE,
            transaction__reason="dev_payment_settle",
            amount_cents__gt=0,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).aggregate(total=Sum("amount_cents"))["total"]
        or 0
    )
    # Unresolved orders can still settle, regardless of their age.
    reserved = (
        DevPaymentOrder.objects.filter(
            user=user,
            kind="payin",
            financial_state="pending",
        ).aggregate(total=Sum("amount_cents"))["total"]
        or 0
    )
    if paid + reserved + amount_cents > limit:
        raise ValidationError(
            "Daily test-deposit limit reached; pending orders count until resolved"
        )


def create(user, *, client_key, kind, method, amount_cents):
    require_dev()
    if not user.email_verified:
        raise ValidationError("Verify your email before testing payments")
    if (
        kind not in {"payin", "payout"}
        or not isinstance(amount_cents, int)
        or isinstance(amount_cents, bool)
        or not 0 < amount_cents <= 49999
    ):
        raise ValidationError("Invalid development payment")
    if method not in (
        PAYIN_METHODS if kind == "payin" else {"cash_app", "paypal", "chime"}
    ):
        raise ValidationError("Invalid payment method")
    if kind == "payin":
        try:
            validate_payin_amount(PAYIN_METHODS[method], amount_cents)
        except ValueError as error:
            raise ValidationError(str(error)) from error
    vendor = client()
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        previous = DevPaymentOrder.objects.filter(
            user=user, client_key=client_key
        ).first()
        if previous:
            if (previous.kind, previous.method, previous.amount_cents) != (
                kind,
                method,
                amount_cents,
            ):
                raise ValidationError("Request key was used for a different payment")
            return previous
        if kind == "payin":
            _require_deposit_allowed(user, amount_cents)
        a = accounts(user)
        if (
            kind == "payout"
            and account_balance_cents(a["player_available"]) < amount_cents
        ):
            raise ValidationError("Insufficient test credits")
        order = DevPaymentOrder.objects.create(
            user=user,
            client_key=client_key,
            kind=kind,
            method=method,
            amount_cents=amount_cents,
        )
        if kind == "payout":
            post_transaction(
                idempotency_key=f"dpdev:hold:{order.id}",
                reason="dev_payment_hold",
                legs=[
                    (a["player_available"].id, -amount_cents),
                    (a["player_held"].id, amount_cents),
                ],
                reference=str(order.id),
            )
        order.submitted = True
        order.save(update_fields=["submitted"])
    # Persisted before dispatch. Transport failure never triggers a fresh retry.
    try:
        if kind == "payin":
            reply = vendor.create_payin(
                order_sn=order.id.hex,
                user_name=user.id.hex,
                method=PAYIN_METHODS[method],
                amount_cents=amount_cents,
                notify_url="https://dev.dollarpay.invalid/notify/payin",
                ip="127.0.0.1",
                device_id="development-only",
                return_url="https://dev.dollarpay.invalid/return",
            )
        else:
            reply = vendor.create_payout(
                order_sn=order.id.hex,
                method=method,
                recipient="test@example.com"
                if method == "paypal"
                else "$development-only",
                amount_cents=amount_cents,
                notify_url="https://dev.dollarpay.invalid/notify/payout",
            )
        order.provider_transaction_id = reply.get("transaction_id", "")
        order.save(update_fields=["provider_transaction_id", "updated_at"])
    except (DollarPayError, ValueError):
        order.state = "review"
        order.review_reason = (
            "Submission outcome is uncertain; reconcile this order, do not resubmit"
        )
        order.save(update_fields=["state", "review_reason", "updated_at"])
    order.refresh_from_db()
    return order


@transaction.atomic
def receive(payload, kind, *, from_reconcile=False):
    require_dev()
    if (
        not isinstance(payload, dict)
        or len(payload) > 40
        or any(
            not isinstance(k, str)
            or not isinstance(v, (str, int))
            or isinstance(v, bool)
            or len(str(v)) > 512
            for k, v in payload.items()
        )
        or payload.get("merchant_id") != MERCHANT
        or not verify_signature(payload, KEY)
    ):
        raise ValidationError("Invalid development notification")
    try:
        candidate = DevPaymentOrder.objects.get(
            pk=payload.get("outer_order_sn"), kind=kind
        )
        get_user_model().objects.select_for_update().get(pk=candidate.user_id)
        order = DevPaymentOrder.objects.select_for_update().get(pk=candidate.pk)
    except (DevPaymentOrder.DoesNotExist, ValueError, DjangoValidationError):
        raise ValidationError("Unknown development order")
    digest = _payload_digest(payload)
    if DevPaymentEvent.objects.filter(payload_sha256=digest).exists():
        return order
    status = str(payload.get("pay_status", ""))
    state = order.financial_state
    a = accounts(order.user)
    amount = order.amount_cents
    reason = ""
    if order.state == "review" and not from_reconcile:
        reason = order.review_reason or "Explicit reconciliation required"
    elif _amount_cents(payload.get("primary_amount", payload.get("amount"))) != amount:
        reason = "Notification amount mismatch"
    elif payload.get("status") != "00000" or not payload.get("transaction_id"):
        reason = "Notification requires review"
    elif (
        order.provider_transaction_id
        and order.provider_transaction_id != payload["transaction_id"]
    ):
        reason = "Transaction identity mismatch"
    elif status == "0":
        pass  # Late processing events cannot undo a terminal settlement.
    elif status == "1" and state in {"pending", "succeeded"}:
        if kind == "payin":
            legs = [
                (a["player_available"].id, amount),
                (a["payment_clearing"].id, -amount),
            ]
        else:
            if state == "pending" and account_balance_cents(a["player_held"]) < amount:
                raise ValidationError("Test payout reservation is missing")
            legs = [(a["player_held"].id, -amount), (a["payment_clearing"].id, amount)]
        post_transaction(
            idempotency_key=f"dpdev:settle:{order.id}",
            reason="dev_payment_settle",
            legs=legs,
            reference=str(order.id),
        )
        order.state = "succeeded"
    elif status == "5" and state in {"pending", "failed"}:
        if kind == "payout":
            post_transaction(
                idempotency_key=f"dpdev:release:{order.id}",
                reason="dev_payment_release",
                legs=[
                    (a["player_held"].id, -amount),
                    (a["player_available"].id, amount),
                ],
                reference=str(order.id),
            )
        order.state = "failed"
    elif status == "4" and kind == "payin" and state in {"succeeded", "refunded"}:
        if (
            state != "refunded"
            and account_balance_cents(a["player_available"]) < amount
        ):
            reason = "Insufficient test credits for refund; review required"
        else:
            post_transaction(
                idempotency_key=f"dpdev:refund:{order.id}",
                reason="dev_payment_refund",
                legs=[
                    (a["player_available"].id, -amount),
                    (a["payment_clearing"].id, amount),
                ],
                reference=str(order.id),
            )
            order.state = "refunded"
    else:
        reason = "Conflicting notification transition"
    if reason:
        order.state = "review"
        order.review_reason = reason
    else:
        if status != "0":
            order.financial_state = order.state
            order.review_reason = ""
    if not order.provider_transaction_id:
        order.provider_transaction_id = str(payload.get("transaction_id", ""))[:120]
    order.save(
        update_fields=[
            "state",
            "financial_state",
            "review_reason",
            "provider_transaction_id",
            "updated_at",
        ]
    )
    DevPaymentEvent.objects.create(
        order=order,
        payload_sha256=digest,
        pay_status=status[:10],
        recorded_state=order.state,
    )
    return order


def simulate(user, order, outcome):
    require_dev()
    if order.user_id != user.pk:
        raise NotFound()
    if outcome not in {"success", "failure", "refund"}:
        raise ValidationError("Invalid test result")
    gateway = DevGatewayOrder.objects.filter(order=order).first()
    if not gateway:
        raise ValidationError("Order needs reconciliation")
    status = {"success": "1", "failure": "5", "refund": "4"}[outcome]
    if order.kind == "payout" and status == "4":
        raise ValidationError("Payout refunds are not supported")
    # Gateway state is persisted, so reconciliation can recover a lost callback.
    gateway.pay_status = status
    gateway.save(update_fields=["pay_status"])
    payload = _reply(order, gateway)
    payload.pop("sign")
    payload.pop("pay_url")
    payload["pay_time"] = timezone.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    return receive(_signed(payload), order.kind)


def reconcile(user, order):
    require_dev()
    if order.user_id != user.pk:
        raise NotFound()
    try:
        reply = (
            client().query_payin(order.id.hex)
            if order.kind == "payin"
            else client().query_payout(order.id.hex)
        )
    except DollarPayRejected:
        # Only the local simulator can prove absence after dispatch has ended.
        # Never apply this inference to the real merchant API.
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=user.pk)
            order = DevPaymentOrder.objects.select_for_update().get(pk=order.pk)
            if (
                order.state != "review"
                or order.financial_state != "pending"
                or DevGatewayOrder.objects.filter(order=order).exists()
            ):
                raise
            gateway = DevGatewayOrder.objects.create(
                order=order, transaction_id=f"dev-{order.id.hex}", pay_status="5"
            )
            return receive(_reply(order, gateway), order.kind, from_reconcile=True)
    # Signed processing confirms no terminal outcome, not a failed transfer.
    if reply["pay_status"] == "0":
        return order
    return receive(reply, order.kind, from_reconcile=True)
