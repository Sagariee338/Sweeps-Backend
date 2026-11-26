"""Recovery boundaries: typed payloads, active owners and single-use tokens."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from .email_flows import email_verification_token_generator
from .models import User


class RecoveryValidationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="recovery@example.invalid", password="initial-unique-password", email_verified=True,
        )
        self.api = APIClient()

    def params(self, generator=default_token_generator):
        return {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": generator.make_token(self.user),
        }

    def test_malformed_links_and_password_types_return_validation_errors(self):
        valid = self.params()
        malformed_uid = urlsafe_base64_encode(b"not-a-uuid")
        for payload in [
            {}, {**valid, "uid": malformed_uid}, {**valid, "uid": []},
            {**valid, "token": []}, {**valid, "password": []},
            {**valid, "password": True}, {**valid, "password": {"value": "invalid"}},
        ]:
            with self.subTest(payload_keys=list(payload)):
                response = self.api.post("/api/v1/auth/password-reset/confirm/", payload, format="json")
                self.assertEqual(response.status_code, 400)
        for payload in [{"uid": malformed_uid, "token": "invalid"}, {"uid": [], "token": []}]:
            self.assertEqual(self.api.post("/api/v1/auth/verify-email/", payload, format="json").status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("initial-unique-password"))

    def test_inactive_accounts_cannot_consume_recovery_or_verification_tokens(self):
        reset = self.params()
        self.user.email_verified = False
        verify = self.params(email_verification_token_generator)
        self.user.is_active = False
        self.user.save(update_fields=["is_active", "email_verified"])
        self.assertEqual(self.api.post("/api/v1/auth/password-reset/confirm/", {
            **reset, "password": "replacement-unique-password",
        }, format="json").status_code, 400)
        self.assertEqual(self.api.post("/api/v1/auth/verify-email/", verify, format="json").status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)
        self.assertTrue(self.user.check_password("initial-unique-password"))

    def test_password_reset_preserves_spaces_and_login_accepts_exact_password(self):
        password = "  spaced-unique-recovery-password  "
        self.assertEqual(self.api.post("/api/v1/auth/password-reset/confirm/", {
            **self.params(), "password": password,
        }, format="json").status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(password))
        self.assertFalse(self.user.check_password(password.strip()))
        self.assertEqual(self.api.post("/api/v1/auth/login/", {
            "email": self.user.email, "password": password,
        }, format="json").status_code, 200)

    def test_reset_invalidates_previous_authenticated_sessions(self):
        session = APIClient()
        self.assertTrue(session.login(email=self.user.email, password="initial-unique-password"))
        self.assertEqual(session.get("/api/v1/auth/me/").status_code, 200)
        self.user.refresh_from_db()  # Login updates the token's last_login input.
        self.assertEqual(self.api.post("/api/v1/auth/password-reset/confirm/", {
            **self.params(), "password": "session-replacement-unique-password",
        }, format="json").status_code, 200)
        self.assertEqual(session.get("/api/v1/auth/me/").status_code, 403)
        self.assertEqual(session.post("/api/v1/auth/login/", {
            "email": self.user.email, "password": "session-replacement-unique-password",
        }, format="json").status_code, 200)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_requests_validate_shape_and_keep_unknown_accounts_generic(self):
        for path in ["password-reset/request", "verify-email/resend"]:
            for payload in [{}, {"email": []}, {"email": "invalid"}, {"email": True}]:
                self.assertEqual(self.api.post(f"/api/v1/auth/{path}/", payload, format="json").status_code, 400)
            known = self.api.post(f"/api/v1/auth/{path}/", {"email": self.user.email}, format="json")
            unknown = self.api.post(f"/api/v1/auth/{path}/", {"email": "unknown@example.invalid"}, format="json")
            self.assertEqual(known.status_code, 200)
            self.assertEqual(unknown.status_code, 200)
            self.assertEqual(known.data, unknown.data)
            cache.clear()
        self.assertEqual(len(mail.outbox), 1)


class RecoveryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        cache.clear()

    def test_concurrent_password_reset_consumes_token_once(self):
        user = User.objects.create_user(email="reset-race@example.invalid", password="original-unique-password")
        payload = {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
        start = Barrier(2)

        def reset(index):
            close_old_connections()
            try:
                start.wait(timeout=10)
                return APIClient().post("/api/v1/auth/password-reset/confirm/", {
                    **payload, "password": f"unique-replacement-password-{index}",
                }, format="json").status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            statuses = list(workers.map(reset, range(2)))
        self.assertEqual(sorted(statuses), [200, 400])

    def test_reset_and_authenticated_password_change_cannot_overwrite_each_other(self):
        user = User.objects.create_user(email="change-race@example.invalid", password="original-unique-password")
        payload = {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
        start = Barrier(2)

        def change(kind):
            close_old_connections()
            try:
                api = APIClient()
                if kind == "authenticated":
                    api.force_authenticate(user=user)
                start.wait(timeout=10)
                if kind == "reset":
                    return api.post("/api/v1/auth/password-reset/confirm/", {
                        **payload, "password": "recovered-unique-password",
                    }, format="json").status_code
                return api.post("/api/v1/auth/password/", {
                    "current_password": "original-unique-password",
                    "new_password": "changed-unique-password",
                }, format="json").status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            statuses = list(workers.map(change, ["reset", "authenticated"]))
        self.assertEqual(sorted(statuses), [200, 400])
