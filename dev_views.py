from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from drf_spectacular.utils import extend_schema

from integrations.models import DevPaymentOrder
from . import development as service
from .client import DollarPayError


class CreateInput(serializers.Serializer):
    client_key = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["payin", "payout"])
    method = serializers.ChoiceField(
        choices=["cash_app", "apple_pay", "google_pay", "card", "paypal", "chime"]
    )
    amount_cents = serializers.IntegerField(min_value=1, max_value=49999)


class SimulateInput(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["success", "failure", "refund"])


class DevOrderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    method = serializers.CharField()
    amount_cents = serializers.IntegerField()
    currency = serializers.CharField()
    state = serializers.CharField()
    checkout_path = serializers.CharField(allow_null=True)
    review_reason = serializers.CharField()
    created_at = serializers.DateTimeField()


class DevWalletSerializer(serializers.Serializer):
    currency = serializers.CharField()
    available_cents = serializers.IntegerField()
    held_cents = serializers.IntegerField()


class DevNotificationSerializer(serializers.Serializer):
    merchant_id = serializers.CharField()
    outer_order_sn = serializers.CharField()
    transaction_id = serializers.CharField()
    status = serializers.CharField()
    pay_status = serializers.ChoiceField(choices=["0", "1", "4", "5"])
    primary_amount = serializers.CharField()
    amount = serializers.CharField(required=False)
    pay_time = serializers.CharField(required=False)
    sign = serializers.CharField()


class DevelopmentView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "development_payments"

    def initial(self, request, *args, **kwargs):
        service.require_dev()
        super().initial(request, *args, **kwargs)

    def response(self, value, status=200):
        result = Response(value, status=status)
        result["Cache-Control"] = "no-store"
        return result

    def order(self, request, order_id):
        return get_object_or_404(DevPaymentOrder, user=request.user, pk=order_id)


class WalletView(DevelopmentView):
    @extend_schema(tags=["Development payments"], responses=DevWalletSerializer)
    def get(self, request):
        return self.response(service.wallet(request.user))


class OrdersView(DevelopmentView):
    @extend_schema(
        tags=["Development payments"], responses=DevOrderSerializer(many=True)
    )
    def get(self, request):
        return self.response(
            [
                service.data(x)
                for x in DevPaymentOrder.objects.filter(user=request.user).order_by(
                    "-created_at"
                )[:50]
            ]
        )

    @extend_schema(
        tags=["Development payments"], request=CreateInput, responses=DevOrderSerializer
    )
    def post(self, request):
        payload = CreateInput(data=request.data)
        payload.is_valid(raise_exception=True)
        result = service.create(request.user, **payload.validated_data)
        return self.response(
            service.data(result), status=202 if result.state == "review" else 201
        )


class OrderView(DevelopmentView):
    @extend_schema(tags=["Development payments"], responses=DevOrderSerializer)
    def get(self, request, order_id):
        return self.response(service.data(self.order(request, order_id)))


class SimulateView(DevelopmentView):
    @extend_schema(
        tags=["Development payments"],
        request=SimulateInput,
        responses=DevOrderSerializer,
    )
    def post(self, request, order_id):
        payload = SimulateInput(data=request.data)
        payload.is_valid(raise_exception=True)
        order = service.simulate(
            request.user,
            self.order(request, order_id),
            payload.validated_data["outcome"],
        )
        return self.response(service.data(order))


class ReconcileView(DevelopmentView):
    @extend_schema(
        tags=["Development payments"], request=None, responses=DevOrderSerializer
    )
    def post(self, request, order_id):
        try:
            order = service.reconcile(request.user, self.order(request, order_id))
        except DollarPayError:
            return self.response(
                {
                    "detail": "No signed gateway outcome is available; the reservation remains held"
                },
                status=409,
            )
        return self.response(service.data(order))


class NotifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # Webhook authenticity is the verified signature.

    @extend_schema(
        tags=["Development payments"],
        request=DevNotificationSerializer,
        responses={(200, "text/plain"): str},
    )
    def post(self, request, kind):
        service.receive(request.data, kind)
        return HttpResponse("SUCCESS", content_type="text/plain")
