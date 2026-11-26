import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from catalog.models import Provider
from demo.models import DemoPayment
from integrations.models import DevPaymentOrder
from provider_accounts.models import (
    ProviderAccountAuditEvent,
    ProviderConnection,
    ProviderPlayerAccount,
)


@override_settings(DEBUG=True, DEMO_MODE=False, DOLLARPAY_DEV_MODE=True)
class AccountUpdateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="updates@example.invalid", password="long-private-test-password"
        )
        self.other = get_user_model().objects.create_user(
            email="other-updates@example.invalid", password="long-private-test-password"
        )
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_test_payments_are_owner_scoped_and_legacy_demo_records_hidden(self):
        DemoPayment.objects.create(
            user=self.user, client_key="legacy", amount_cents=1099
        )
        for user in [self.user, self.other]:
            DevPaymentOrder.objects.create(
                user=user,
                client_key=uuid.uuid4(),
                kind="payin",
                method="cash_app",
                amount_cents=1099,
            )
        response = self.api.get("/api/v1/auth/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(row["kind"], row["title"]) for row in response.data],
            [("test_payment", "Test deposit")],
        )
        self.assertEqual(response["Cache-Control"], "no-store")
        with override_settings(DEBUG=False):
            self.assertEqual(self.api.get("/api/v1/auth/notifications/").data, [])

    def test_game_updates_follow_account_owner_and_never_include_logins(self):
        provider = Provider.objects.create(code="juwa2", name="Juwa2")
        connection = ProviderConnection.objects.create(
            provider=provider,
            code="updates-free",
            environment="production",
            mode="free_play",
            adapter="juwa2",
        )
        for user in [self.user, self.other]:
            account = ProviderPlayerAccount.objects.create(
                user=user,
                connection=connection,
                external_account=f"private-player-{user.id}",
                encrypted_password="never-expose-password",
                state="active",
            )
            ProviderAccountAuditEvent.objects.create(
                account=account,
                actor=self.user,
                action="credential_reveal",
                from_state="active",
                to_state="active",
            )
        response = self.api.get("/api/v1/auth/notifications/")
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Juwa2 · Free play login viewed")
        self.assertEqual(response.data[0]["kind"], "game_account")
        self.assertNotIn("private-player", str(response.data))
        self.assertNotIn("never-expose-password", str(response.data))
        connection.environment = "mock"
        ProviderConnection.objects.filter(pk=connection.pk).update(environment="mock")
        self.assertEqual(self.api.get("/api/v1/auth/notifications/").data, [])
