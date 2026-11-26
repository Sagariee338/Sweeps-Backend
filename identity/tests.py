from django.test import TestCase
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
from django.db import IntegrityError
from rest_framework.test import APIClient
from .models import User
from wallet.models import LedgerAccount


class AccountApiTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_registration_creates_account_and_empty_wallet(self):
        client = APIClient()
        response = client.post("/api/v1/auth/register/", {
            "email": "new@example.com", "password": "a-long-unique-test-password",
            "display_name": "New Player",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.email_verified, settings.DEMO_MODE)
        self.assertEqual(LedgerAccount.objects.filter(owner=user).count(), 2)
        client.force_authenticate(user=user)
        wallet = client.get("/api/v1/wallet/")
        self.assertEqual(wallet.status_code, 200)
        self.assertEqual(wallet.json()["available_cents"], 0)

    def test_registration_rejects_password_similar_to_email_or_name(self):
        client = APIClient()
        response = client.post("/api/v1/auth/register/", {
            "email": "longplayername@example.com", "password": "longplayername1234",
            "display_name": "Long Player Name",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="longplayername@example.com").exists())
        name_response = client.post("/api/v1/auth/register/", {
            "email": "unrelated@example.com", "password": "longplayername1234",
            "display_name": "Long Player Name",
        }, format="json")
        self.assertEqual(name_response.status_code, 400)

    def test_registration_returns_validation_error_for_concurrent_duplicate(self):
        client = APIClient()
        with patch("identity.models.UserManager.create_user", side_effect=IntegrityError("duplicate key")):
            response = client.post("/api/v1/auth/register/", {
                "email": "race@example.com", "password": "unique-test-password-long",
                "display_name": "Race Player",
            }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_profile_password_and_play_control(self):
        user = User.objects.create_user(email="controls@example.com", password="current-long-password", email_verified=True)
        client = APIClient()
        client.force_authenticate(user=user)
        profile = client.post("/api/v1/auth/profile/", {"display_name": "Player One"}, format="json")
        self.assertEqual(profile.data["display_name"], "Player One")
        wrong = client.post("/api/v1/auth/password/", {
            "current_password": "bad", "new_password": "another-unique-long-password"
        }, format="json")
        self.assertEqual(wrong.status_code, 400)
        changed = client.post("/api/v1/auth/password/", {
            "current_password": "current-long-password", "new_password": "another-unique-long-password"
        }, format="json")
        self.assertEqual(changed.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("another-unique-long-password"))
        excluded = client.post("/api/v1/auth/play-control/", {"days": 1}, format="json")
        self.assertEqual(excluded.status_code, 200)
        self.assertTrue(excluded.data["is_excluded"])
        if settings.DEMO_MODE:
            blocked = client.post("/api/v1/demo/payments/", {
                "client_key": "blocked", "amount_cents": 999, "method": "cash_app", "simulate": "succeeded",
            }, format="json")
            self.assertEqual(blocked.status_code, 400)

    def test_notifications_are_owner_scoped(self):
        from support.models import Ticket
        first = User.objects.create_user(email="first@notice.example", password="long-unique-password")
        second = User.objects.create_user(email="second@notice.example", password="long-unique-password")
        Ticket.objects.create(user=first, category="account", subject="Private issue", message="Test")
        client = APIClient()
        client.force_authenticate(user=second)
        self.assertEqual(client.get("/api/v1/auth/notifications/").data, [])
        client.force_authenticate(user=first)
        self.assertEqual(client.get("/api/v1/auth/notifications/").data[0]["title"], "Private issue")

    @override_settings(DEMO_MODE=False, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_verification_and_password_reset(self):
        client = APIClient()
        with self.captureOnCommitCallbacks(execute=True):
            created = client.post("/api/v1/auth/register/", {
                "email": "verify@example.com", "password": "initial-unique-long-password",
                "display_name": "Verify Player",
            }, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        denied = client.post("/api/v1/auth/login/", {
            "email": "verify@example.com", "password": "initial-unique-long-password",
        }, format="json")
        self.assertEqual(denied.status_code, 400)
        resent = client.post("/api/v1/auth/verify-email/resend/", {"email": "verify@example.com"}, format="json")
        self.assertEqual(resent.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        link = mail.outbox[0].body.splitlines()[2]
        params = {key: values[0] for key, values in parse_qs(urlparse(link).query).items()}
        crossed = client.post("/api/v1/auth/password-reset/confirm/", {
            **params, "password": "crossed-unique-long-password",
        }, format="json")
        self.assertEqual(crossed.status_code, 400)
        verified = client.post("/api/v1/auth/verify-email/", params, format="json")
        self.assertEqual(verified.status_code, 200)
        requested = client.post("/api/v1/auth/password-reset/request/", {"email": "verify@example.com"}, format="json")
        self.assertEqual(requested.status_code, 200)
        reset_link = mail.outbox[-1].body.splitlines()[2]
        reset_params = {key: values[0] for key, values in parse_qs(urlparse(reset_link).query).items()}
        crossed = client.post("/api/v1/auth/verify-email/", reset_params, format="json")
        self.assertEqual(crossed.status_code, 400)
        reset = client.post("/api/v1/auth/password-reset/confirm/", {
            **reset_params, "password": "new-unique-long-password",
        }, format="json")
        self.assertEqual(reset.status_code, 200)
        reused = client.post("/api/v1/auth/password-reset/confirm/", {
            **reset_params, "password": "another-unique-long-password",
        }, format="json")
        self.assertEqual(reused.status_code, 400)
