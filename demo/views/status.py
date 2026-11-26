"""Local-demo mode disclosure."""
from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view
from config.api_schemas import DemoStatusSerializer


@extend_schema_view(get=extend_schema(responses=DemoStatusSerializer, tags=["Local demo"]))
class DemoStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "demo_mode": settings.DEMO_MODE, "database": "postgresql",
            "money_is_real": False, "provider_is_real": False,
        })
