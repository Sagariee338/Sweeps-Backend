"""Session authentication, registration, and email recovery."""
from django.conf import settings
from django.contrib.auth import login, logout, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view
from config.api_schemas import CsrfSerializer, RegistrationResponseSerializer, StatusSerializer, UserEnvelopeSerializer
from wallet.models import LedgerAccount
from ..email_flows import send_password_reset, send_verification, verified_token_user
from ..models import User
from ..serializers import (
    EmailInput, LoginSerializer, RegisterSerializer, ResetPasswordInput,
    UserSerializer, VerifyTokenInput,
)


@method_decorator(ensure_csrf_cookie, name="dispatch")
@extend_schema_view(get=extend_schema(responses=CsrfSerializer, tags=["Authentication"], summary="Set the CSRF cookie"))
class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrf": "cookie-set"})


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(post=extend_schema(request=RegisterSerializer, responses={201: RegistrationResponseSerializer}, tags=["Authentication"]))
class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @transaction.atomic
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = serializer.save()
        except IntegrityError:
            return Response({"email": "An account with this email already exists"}, status=status.HTTP_400_BAD_REQUEST)
        if settings.DEMO_MODE:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
        LedgerAccount.objects.create(owner=user, kind=LedgerAccount.Kind.PLAYER_AVAILABLE, currency="USD")
        LedgerAccount.objects.create(owner=user, kind=LedgerAccount.Kind.PLAYER_HELD, currency="USD")
        if settings.DEMO_MODE:
            login(request, user)
        else:
            transaction.on_commit(lambda: send_verification(user))
        return Response({
            "user": UserSerializer(user).data,
            "next_step": "demo_ready" if settings.DEMO_MODE else "email_verification_required",
        }, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
@extend_schema_view(post=extend_schema(request=LoginSerializer, responses=UserEnvelopeSerializer, tags=["Authentication"]))
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login(request, serializer.validated_data["user"])
        return Response({"user": UserSerializer(request.user).data})


@extend_schema_view(post=extend_schema(request=None, responses={204: None}, tags=["Authentication"]))
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(post=extend_schema(request=VerifyTokenInput, responses=StatusSerializer, tags=["Authentication"]))
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @transaction.atomic
    def post(self, request):
        payload = VerifyTokenInput(data=request.data)
        payload.is_valid(raise_exception=True)
        user = verified_token_user(**payload.validated_data, purpose="verify", for_update=True)
        if not user or user.email_verified:
            return Response({"detail": "Verification link is invalid or expired"}, status=status.HTTP_400_BAD_REQUEST)
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        return Response({"status": "verified"})


@extend_schema_view(post=extend_schema(request=EmailInput, responses=StatusSerializer, tags=["Authentication"]))
class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        payload = EmailInput(data=request.data)
        payload.is_valid(raise_exception=True)
        email = payload.validated_data["email"].lower().strip()
        if email:
            user = User.objects.filter(email=email, is_active=True, email_verified=False).first()
            if user:
                send_verification(user)
        return Response({"status": "If this address needs verification, a new link has been sent."})


@extend_schema_view(post=extend_schema(request=EmailInput, responses=StatusSerializer, tags=["Authentication"]))
class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        payload = EmailInput(data=request.data)
        payload.is_valid(raise_exception=True)
        email = payload.validated_data["email"].lower().strip()
        user = None
        if email:
            user = User.objects.filter(email=email, is_active=True).first()
        if user:
            send_password_reset(user)
        return Response({"status": "If an account exists, a reset link has been sent."})


@extend_schema_view(post=extend_schema(request=ResetPasswordInput, responses=StatusSerializer, tags=["Authentication"]))
class ConfirmPasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @transaction.atomic
    def post(self, request):
        payload = ResetPasswordInput(data=request.data)
        payload.is_valid(raise_exception=True)
        user = verified_token_user(
            payload.validated_data["uid"], payload.validated_data["token"],
            purpose="reset", for_update=True,
        )
        if not user:
            return Response({"detail": "Reset link is invalid or expired"}, status=status.HTTP_400_BAD_REQUEST)
        password = payload.validated_data["password"]
        try:
            password_validation.validate_password(password, user)
        except DjangoValidationError as error:
            raise ValidationError({"password": error.messages}) from error
        user.set_password(password)
        user.save(update_fields=["password"])
        return Response({"status": "password_reset"})
