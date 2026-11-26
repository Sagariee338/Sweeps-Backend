"""Fake payout HTTP endpoints."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view
from config.api_schemas import RedemptionEnvelopeSerializer, RedemptionOrderSerializer
from ..models import DemoRedemption
from ..serializers import DemoRedemptionInput, DemoResolveRedemptionInput
from ..services.redemptions import create_redemption, redemption_data, resolve_redemption
from ..services.wallets import balances


@extend_schema_view(get=extend_schema(responses=RedemptionOrderSerializer(many=True), tags=["Demo redemptions"]), post=extend_schema(request=DemoRedemptionInput, responses={201: RedemptionEnvelopeSerializer}, tags=["Demo redemptions"]))
class DemoRedemptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response([redemption_data(item) for item in DemoRedemption.objects.filter(user=request.user)[:50]])

    def post(self, request):
        serializer = DemoRedemptionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_redemption(request.user, serializer.validated_data)
        return Response({"redemption": redemption_data(order), "wallet": balances(request.user)}, status=status.HTTP_201_CREATED)


@extend_schema_view(post=extend_schema(request=DemoResolveRedemptionInput, responses=RedemptionEnvelopeSerializer, tags=["Demo redemptions"]))
class DemoRedemptionResolveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        serializer = DemoResolveRedemptionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = resolve_redemption(request.user, order_id, serializer.validated_data["status"])
        return Response({"redemption": redemption_data(order), "wallet": balances(request.user)})
