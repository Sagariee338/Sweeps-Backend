"""Shared local-demo guards and account helpers."""
import hashlib
import hmac
import json
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from identity.models import PlayControl
from identity.services import apply_pending_limit
from wallet.models import LedgerAccount
from ..models import DemoPayment


def _request_fingerprint(kind, data):
    encoded = json.dumps({"kind": kind, **data}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), encoded, hashlib.sha256).hexdigest()


def _lock_user(user):
    get_user_model().objects.select_for_update().get(pk=user.pk)


def _require_play_allowed(user):
    control = PlayControl.objects.filter(user=user).first()
    if control and control.excluded_until and control.excluded_until > timezone.now():
        raise ValidationError("Play is paused until your exclusion period ends")


def _require_funding_limit(user, amount):
    control = PlayControl.objects.filter(user=user).first()
    if not control:
        return
    apply_pending_limit(control)
    limit = control.daily_funding_limit_cents
    if limit is None:
        return
    spent = DemoPayment.objects.filter(
        user=user, status=DemoPayment.State.SUCCEEDED,
        updated_at__gte=timezone.now() - timedelta(hours=24),
    ).aggregate(total=Sum("amount_cents"))["total"] or 0
    if spent + amount > limit:
        raise ValidationError("Daily demo funding limit reached")


def _account(user, kind):
    account, _ = LedgerAccount.objects.get_or_create(owner=user, kind=kind, currency="USD")
    return account
