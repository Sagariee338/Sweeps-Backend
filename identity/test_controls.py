from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from identity.models import PlayControl


class ControlValidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="controls-validation@example.invalid",
            password="long-private-password",
        )
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_pause_rejects_boolean_fractional_and_missing_duration_without_mutation(
        self,
    ):
        for payload in [{}, {"days": True}, {"days": 1.0}, {"days": []}, {"days": 0}]:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.api.post(
                        "/api/v1/auth/play-control/", payload, format="json"
                    ).status_code,
                    400,
                )
        self.assertFalse(PlayControl.objects.filter(user=self.user).exists())

    def test_limit_requires_explicit_value_and_rejects_fractional_values(self):
        self.api.post(
            "/api/v1/auth/play-control/funding-limit/",
            {"amount_cents": 1000},
            format="json",
        )
        for payload in [
            {},
            {"amount_cents": True},
            {"amount_cents": 1000.0},
            {"amount_cents": -1},
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.api.post(
                        "/api/v1/auth/play-control/funding-limit/",
                        payload,
                        format="json",
                    ).status_code,
                    400,
                )
        self.assertEqual(
            PlayControl.objects.get(user=self.user).daily_funding_limit_cents, 1000
        )
        self.assertEqual(
            self.api.post(
                "/api/v1/auth/play-control/funding-limit/",
                {"amount_cents": None},
                format="json",
            ).status_code,
            200,
        )
