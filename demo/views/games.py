"""Local game launch and round HTTP endpoints."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view
from config.api_schemas import GameLaunchSerializer, GameRoundEnvelopeSerializer, GameRoundSerializer
from rest_framework import serializers
from ..models import DemoGameRound
from ..serializers import DemoSpinInput
from ..services.games import create_game_session, round_data, spin
from ..services.wallets import balances


class RoundHistorySerializer(GameRoundSerializer):
    game_slug = serializers.SlugField()
    game_title = serializers.CharField()


class DemoRoundHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=RoundHistorySerializer(many=True), tags=["Demo games"])
    def get(self, request):
        rounds = DemoGameRound.objects.filter(
            session__user=request.user, session__game__provider__code="demo",
        ).select_related("session__game").order_by("-created_at", "-id")[:50]
        response = Response([{
            **round_data(round_), "game_slug": round_.session.game.slug,
            "game_title": round_.session.game.title,
        } for round_ in rounds])
        response["Cache-Control"] = "no-store"
        return response


@extend_schema_view(post=extend_schema(request=None, responses={201: GameLaunchSerializer}, tags=["Demo games"]))
class DemoGameLaunchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        session = create_game_session(request.user, slug)
        return Response({
            "session_id": str(session.id), "game_slug": slug,
            "launch_url": f"/game/{slug}", "provider": "local_demo",
            "wallet": balances(request.user, session.game),
        }, status=status.HTTP_201_CREATED)


@extend_schema_view(post=extend_schema(request=DemoSpinInput, responses={201: GameRoundEnvelopeSerializer}, tags=["Demo games"]))
class DemoGameSpinView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        serializer = DemoSpinInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        round_, wallet = spin(request.user, slug, serializer.validated_data)
        return Response({
            "round": round_data(round_),
            "wallet": wallet,
        }, status=status.HTTP_201_CREATED)
