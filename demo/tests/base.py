"""Shared PostgreSQL demo API fixture."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from catalog.models import Game, Provider


class DemoApiTestCase(TestCase):
    def setUp(self):
        if not settings.DEMO_MODE:
            self.skipTest("Demo API is intentionally disabled")
        self.user = get_user_model().objects.create_user(
            email="demo-player@example.com", password="long-demo-test-password", email_verified=True
        )
        self.other = get_user_model().objects.create_user(
            email="other-player@example.com", password="long-demo-test-password", email_verified=True
        )
        provider = Provider.objects.create(code="demo", name="Local Demo", is_active=True)
        self.game = Game.objects.create(
            provider=provider, external_id="test-reels", slug="test-reels",
            title="Test Reels", category="slots", is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
