from django.urls import path
from .views.account import ChangePasswordView, MeView, ProfileView
from .views.auth import (
    ConfirmPasswordResetView, CsrfView, LoginView, LogoutView, RegisterView,
    RequestPasswordResetView, ResendVerificationView, VerifyEmailView,
)
from .views.controls import FundingLimitView, PlayControlView
from .views.notifications import NotificationsView

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="csrf"),
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("password/", ChangePasswordView.as_view(), name="password"),
    path("play-control/", PlayControlView.as_view(), name="play-control"),
    path("play-control/funding-limit/", FundingLimitView.as_view(), name="funding-limit"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("verify-email/resend/", ResendVerificationView.as_view(), name="verify-email-resend"),
    path("password-reset/request/", RequestPasswordResetView.as_view(), name="password-reset-request"),
    path("password-reset/confirm/", ConfirmPasswordResetView.as_view(), name="password-reset-confirm"),
    path("notifications/", NotificationsView.as_view(), name="notifications"),
]
