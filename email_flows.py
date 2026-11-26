"""Single-use account email links, validated by Django's user token generator."""
from urllib.parse import urlencode
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes
from .models import User


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "lavishsweeps.identity.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return super()._make_hash_value(user, timestamp) + str(user.email_verified)


email_verification_token_generator = EmailVerificationTokenGenerator()


def _link(user, path):
    generator = email_verification_token_generator if path == "verify-email" else default_token_generator
    params = urlencode({
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": generator.make_token(user),
    })
    return f"{settings.FRONTEND_URL}/{path}?{params}"


def send_verification(user):
    send_mail(
        "Verify your LavishSweeps email",
        f"Open this link to verify your email address:\n\n{_link(user, 'verify-email')}\n\nIf you did not register, ignore this message.",
        settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
    )


def send_password_reset(user):
    send_mail(
        "Reset your LavishSweeps password",
        f"Open this link to reset your password:\n\n{_link(user, 'reset-password')}\n\nIf you did not request this, ignore this message.",
        settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
    )


def verified_token_user(uid, token, *, purpose, for_update=False):
    try:
        users = User.objects.filter(is_active=True)
        if for_update:
            users = users.select_for_update()
        user = users.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (User.DoesNotExist, ValidationError, ValueError, TypeError, OverflowError):
        return None
    generator = email_verification_token_generator if purpose == "verify" else default_token_generator
    return user if generator.check_token(user, token) else None
