"""Fake pay-in HTTP endpoints."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view
from config.api_schemas import PaymentEnvelopeSerializer, PaymentOrderSerializer
from ..models import DemoPayment
from ..serializers import DemoPaymentInput, DemoResolvePaymentInput
from ..services.payments import create_payment, payment_data, resolve_payment
from ..services.wallets import balances


@extend_schema_view(get=extend_schema(responses=PaymentOrderSerializer(many=True), tags=["Demo payments"]), post=extend_schema(request=DemoPaymentInput, responses={201: PaymentEnvelopeSerializer}, tags=["Demo payments"]))
class DemoPaymentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response([payment_data(item) for item in DemoPayment.objects.filter(user=request.user)[:50]])

    def post(self, request):
        serializer = DemoPaymentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_payment(request.user, serializer.validated_data)
        return Response({"payment": payment_data(order), "wallet": balances(request.user)}, status=status.HTTP_201_CREATED)


@extend_schema_view(post=extend_schema(request=DemoResolvePaymentInput, responses=PaymentEnvelopeSerializer, tags=["Demo payments"]))
class DemoPaymentResolveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        serializer = DemoResolvePaymentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = resolve_payment(request.user, order_id, serializer.validated_data["status"])
        return Response({"payment": payment_data(order), "wallet": balances(request.user)})
