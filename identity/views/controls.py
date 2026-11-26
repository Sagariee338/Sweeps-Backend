"""Player-initiated play pauses and fake-funding limits."""

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view
from config.api_schemas import (
    FundingLimitSerializer,
    PauseResponseSerializer,
    PlayControlSerializer,
)
from ..models import PlayControl
from ..services import apply_pending_limit
from ..serializers import FundingLimitInput, PauseInput


@extend_schema_view(
    get=extend_schema(responses=PlayControlSerializer, tags=["Play controls"]),
    post=extend_schema(
        request=PauseInput, responses=PauseResponseSerializer, tags=["Play controls"]
    ),
)
class PlayControlView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def get(self, request):
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        control, _ = PlayControl.objects.get_or_create(user=request.user)
        control = PlayControl.objects.select_for_update().get(pk=control.pk)
        apply_pending_limit(control)
        active = bool(
            control.excluded_until and control.excluded_until > timezone.now()
        )
        return Response(
            {
                "excluded_until": control.excluded_until,
                "is_excluded": active,
                "daily_funding_limit_cents": control.daily_funding_limit_cents,
                "pending_daily_funding_limit_cents": control.pending_daily_funding_limit_cents,
                "pending_limit_effective_at": control.pending_limit_effective_at,
            }
        )

    @transaction.atomic
    def post(self, request):
        payload = PauseInput(data=request.data)
        payload.is_valid(raise_exception=True)
        days = payload.validated_data["days"]
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        control, _ = PlayControl.objects.get_or_create(user=request.user)
        control = PlayControl.objects.select_for_update().get(pk=control.pk)
        control.excluded_until = max(
            control.excluded_until or timezone.now(),
            timezone.now() + timedelta(days=days),
        )
        control.save(update_fields=["excluded_until", "updated_at"])
        return Response({"excluded_until": control.excluded_until, "is_excluded": True})


@extend_schema_view(
    post=extend_schema(
        request=FundingLimitInput,
        responses=FundingLimitSerializer,
        tags=["Play controls"],
    )
)
class FundingLimitView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        payload = FundingLimitInput(data=request.data)
        payload.is_valid(raise_exception=True)
        amount = payload.validated_data["amount_cents"]
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        control, _ = PlayControl.objects.get_or_create(user=request.user)
        control = PlayControl.objects.select_for_update().get(pk=control.pk)
        apply_pending_limit(control)
        current = control.daily_funding_limit_cents
        if current is None or (amount is not None and amount <= current):
            control.daily_funding_limit_cents = amount
            control.pending_daily_funding_limit_cents = None
            control.pending_limit_effective_at = None
        elif amount != current:
            control.pending_daily_funding_limit_cents = amount
            control.pending_limit_effective_at = timezone.now() + timedelta(hours=24)
        control.save(
            update_fields=[
                "daily_funding_limit_cents",
                "pending_daily_funding_limit_cents",
                "pending_limit_effective_at",
                "updated_at",
            ]
        )
        return Response(
            {
                "daily_funding_limit_cents": control.daily_funding_limit_cents,
                "pending_daily_funding_limit_cents": control.pending_daily_funding_limit_cents,
                "pending_limit_effective_at": control.pending_limit_effective_at,
            }
        )
