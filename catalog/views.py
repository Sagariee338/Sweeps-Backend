from rest_framework import generics
from django.conf import settings
from django.db import models
from rest_framework.permissions import AllowAny
from .models import Game
from .platforms import PLATFORMS
from .serializers import GameSerializer
from provider_accounts.models import ProviderConnection
from integrations.game_clients.gateway import LAUNCHABLE


def _playable_games():
    approved = ProviderConnection.objects.filter(
        is_enabled=True, mode_verified=True, launch_enabled=True,
        mode=ProviderConnection.Mode.FREE_PLAY,
        adapter__in=LAUNCHABLE,
        adapter=models.F("provider__code"),
    ).values("provider_id")
    qs = Game.objects.filter(is_active=True, provider__is_active=True).select_related("provider")
    if not settings.PROVIDER_FREE_PLAY_ENABLED:
        return qs.filter(provider__code="demo") if settings.DEMO_MODE else qs.none()
    if settings.DEMO_MODE:
        return qs.filter(models.Q(provider__code="demo") | models.Q(provider_id__in=approved))
    return qs.filter(provider__code__in=PLATFORMS, provider_id__in=approved)


class GameListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = GameSerializer

    def get_queryset(self):
        qs = _playable_games()
        category = self.request.query_params.get("category")
        search = self.request.query_params.get("search")
        if category:
            qs = qs.filter(category=category)
        if search:
            qs = qs.filter(title__icontains=search[:100])
        return qs


class GameDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = GameSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return _playable_games()
