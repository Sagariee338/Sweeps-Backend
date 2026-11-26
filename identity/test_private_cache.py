"""Private API data must not be cached, including authorization errors."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient


class PrivateApiCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(email="private-cache@example.invalid", password="private-cache-test-password", email_verified=True)
        self.api = APIClient()

    def test_owner_reads_and_metadata_are_not_cached(self):
        self.api.force_authenticate(self.user)
        for path in ["/api/v1/auth/me/", "/api/v1/wallet/", "/api/v1/wallet/transactions/", "/api/v1/me/provider-accounts/", "/api/v1/auth/play-control/", "/api/v1/support/tickets/"]:
            with self.subTest(path=path):
                response = self.api.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get("Cache-Control"), "no-store")
                self.assertIn("Cookie", response.get("Vary", ""))
        self.assertEqual(self.api.head("/api/v1/auth/me/").get("Cache-Control"), "no-store")
        self.assertEqual(self.api.options("/api/v1/auth/me/").get("Cache-Control"), "no-store")

    def test_anonymous_denials_and_unknown_api_paths_are_not_cached(self):
        for path in ["/api/v1/auth/me/", "/api/v1/ops/overview/", "/api/v1/not-a-real-route/"]:
            with self.subTest(path=path):
                response = self.api.get(path)
                self.assertIn(response.status_code, [403, 404])
                self.assertEqual(response.get("Cache-Control"), "no-store")

    def test_validation_and_csrf_failures_are_not_cached(self):
        self.api.force_authenticate(self.user)
        response = self.api.post("/api/v1/auth/profile/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get("Cache-Control"), "no-store")
        csrf = APIClient(enforce_csrf_checks=True).post("/api/v1/auth/login/", {}, format="json")
        self.assertEqual(csrf.status_code, 403)
        self.assertEqual(csrf.get("Cache-Control"), "no-store")

    def test_public_api_is_fresh_and_readiness_is_outside_api_policy(self):
        self.assertEqual(self.api.get("/api/v1/config/").get("Cache-Control"), "no-store")
        self.assertIsNone(self.api.get("/health/").get("Cache-Control"))
