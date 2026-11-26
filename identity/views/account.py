"""Authenticated profile and password changes."""
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view
from config.api_schemas import StatusSerializer
from ..serializers import ChangePasswordSerializer, ProfileSerializer, UserSerializer


@extend_schema_view(get=extend_schema(responses=UserSerializer, tags=["Account"]))
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


@extend_schema_view(post=extend_schema(request=ProfileSerializer, responses=UserSerializer, tags=["Account"]))
class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.display_name = serializer.validated_data["display_name"].strip()
        request.user.save(update_fields=["display_name"])
        return Response(UserSerializer(request.user).data)


@extend_schema_view(post=extend_schema(request=ChangePasswordSerializer, responses=StatusSerializer, tags=["Account"]))
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        # Recheck the current password after serializing recovery/change requests.
        request.user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)
        return Response({"status": "password_changed"})
