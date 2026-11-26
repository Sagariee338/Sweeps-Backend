"""Local wallet balances and per-game transfers."""
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view
from config.api_schemas import GameBalanceSerializer, WalletEnvelopeSerializer, WalletSnapshotSerializer
from catalog.models import Game
from ..serializers import DemoTransferInput
from ..services.games import transfer
from ..services.wallets import balances, game_balance_cents


@extend_schema_view(get=extend_schema(responses=WalletSnapshotSerializer, tags=["Demo wallet"]))
class DemoWalletView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(balances(request.user))


@extend_schema_view(post=extend_schema(request=DemoTransferInput, responses=WalletEnvelopeSerializer, tags=["Demo wallet"]))
class DemoTransfersView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DemoTransferInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"wallet": transfer(request.user, serializer.validated_data)})


@extend_schema_view(get=extend_schema(responses=GameBalanceSerializer(many=True), tags=["Demo wallet"]))
class DemoGameBalancesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        games = Game.objects.select_related("provider").filter(provider__code="demo").order_by("title")
        return Response([{
            "slug": game.slug, "title": game.title,
            "is_active": game.is_active and game.provider.is_active,
            "balance_cents": game_balance_cents(request.user, game),
        } for game in games])
