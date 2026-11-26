"""OpenAPI response shapes for endpoints that assemble dictionaries in APIViews.

These serializers describe the wire format; they do not change runtime validation.
"""
from rest_framework import serializers
from identity.serializers import UserSerializer


class StatusSerializer(serializers.Serializer):
    status = serializers.CharField()


class HealthSerializer(StatusSerializer):
    service = serializers.CharField()


class CsrfSerializer(serializers.Serializer):
    csrf = serializers.CharField()


class UserEnvelopeSerializer(serializers.Serializer):
    user = UserSerializer()


class RegistrationResponseSerializer(UserEnvelopeSerializer):
    next_step = serializers.CharField()


class PlayControlSerializer(serializers.Serializer):
    excluded_until = serializers.DateTimeField(allow_null=True)
    is_excluded = serializers.BooleanField()
    daily_funding_limit_cents = serializers.IntegerField(allow_null=True)
    pending_daily_funding_limit_cents = serializers.IntegerField(allow_null=True)
    pending_limit_effective_at = serializers.DateTimeField(allow_null=True)


class PauseResponseSerializer(serializers.Serializer):
    excluded_until = serializers.DateTimeField()
    is_excluded = serializers.BooleanField()


class FundingLimitSerializer(serializers.Serializer):
    daily_funding_limit_cents = serializers.IntegerField(allow_null=True)
    pending_daily_funding_limit_cents = serializers.IntegerField(allow_null=True)
    pending_limit_effective_at = serializers.DateTimeField(allow_null=True)


class NotificationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class WalletSnapshotSerializer(serializers.Serializer):
    currency = serializers.CharField()
    available_cents = serializers.IntegerField()
    held_cents = serializers.IntegerField()
    provider_balance = serializers.IntegerField(allow_null=True)
    provider_balance_as_of = serializers.DateTimeField(allow_null=True)
    demo_mode = serializers.BooleanField()
    game_balance_cents = serializers.IntegerField(required=False)


class WalletEnvelopeSerializer(serializers.Serializer):
    wallet = WalletSnapshotSerializer()


class WalletTransactionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    reason = serializers.CharField()
    reference = serializers.CharField()
    amount_cents = serializers.IntegerField()
    balance_type = serializers.CharField()
    created_at = serializers.DateTimeField()


class GameBalanceSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    title = serializers.CharField()
    is_active = serializers.BooleanField()
    balance_cents = serializers.IntegerField()


class DemoStatusSerializer(serializers.Serializer):
    demo_mode = serializers.BooleanField()
    database = serializers.CharField()
    money_is_real = serializers.BooleanField()
    provider_is_real = serializers.BooleanField()


class PaymentOrderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    amount_cents = serializers.IntegerField()
    method = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class PaymentEnvelopeSerializer(WalletEnvelopeSerializer):
    payment = PaymentOrderSerializer()


class RedemptionOrderSerializer(PaymentOrderSerializer):
    recipient_masked = serializers.CharField()


class RedemptionEnvelopeSerializer(WalletEnvelopeSerializer):
    redemption = RedemptionOrderSerializer()


class GameLaunchSerializer(WalletEnvelopeSerializer):
    session_id = serializers.UUIDField()
    game_slug = serializers.SlugField()
    launch_url = serializers.CharField()
    provider = serializers.CharField()


class GameRoundSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    symbols = serializers.ListField(child=serializers.CharField())
    choice = serializers.CharField(allow_blank=True)
    outcome = serializers.CharField()
    matched = serializers.BooleanField()
    stake_cents = serializers.IntegerField()
    payout_cents = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class GameRoundEnvelopeSerializer(WalletEnvelopeSerializer):
    round = GameRoundSerializer()


class RuntimeConfigSerializer(serializers.Serializer):
    payment_test_mode = serializers.BooleanField()
    demo_mode = serializers.BooleanField()
    provider_value_accounts_enabled = serializers.BooleanField()
    wallet_movement_enabled = serializers.BooleanField()
