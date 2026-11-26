"""Per-game balances, transfers, and demo ledger isolation."""
from django.test import override_settings
from catalog.models import Game
from .base import DemoApiTestCase


class DemoApiTests(DemoApiTestCase):
    def test_game_credits_cannot_be_spent_or_moved_from_another_game(self):
        other_game = Game.objects.create(
            provider=self.game.provider, external_id="other-reels", slug="other-reels",
            title="Other Reels", category="slots", is_active=True,
        )
        self.client.post("/api/v1/demo/payments/", {
            "client_key": "game-fund", "amount_cents": 1999, "method": "cash_app",
        }, format="json")
        transfer = self.client.post("/api/v1/demo/transfers/", {
            "client_key": "game-transfer", "direction": "to_game",
            "amount_cents": 1000, "game_slug": self.game.slug,
        }, format="json")
        self.assertEqual(transfer.data["wallet"]["game_balance_cents"], 1000)
        self.assertEqual(transfer.data["wallet"]["provider_balance"], 1000)
        other_launch = self.client.post(f"/api/v1/demo/games/{other_game.slug}/launch/", {}, format="json")
        self.assertEqual(other_launch.data["wallet"]["game_balance_cents"], 0)
        other_spin = self.client.post(f"/api/v1/demo/games/{other_game.slug}/spin/", {
            "session_id": other_launch.data["session_id"], "client_key": "wrong-game-spin", "stake_cents": 100,
        }, format="json")
        self.assertEqual(other_spin.status_code, 400)
        other_withdrawal = self.client.post("/api/v1/demo/transfers/", {
            "client_key": "wrong-game-withdrawal", "direction": "from_game",
            "amount_cents": 100, "game_slug": other_game.slug,
        }, format="json")
        self.assertEqual(other_withdrawal.status_code, 400)
        first_launch = self.client.post(f"/api/v1/demo/games/{self.game.slug}/launch/", {}, format="json")
        first_spin = self.client.post(f"/api/v1/demo/games/{self.game.slug}/spin/", {
            "session_id": first_launch.data["session_id"], "client_key": "right-game-spin", "stake_cents": 100,
        }, format="json")
        self.assertEqual(first_spin.status_code, 201)
        self.assertEqual(first_spin.data["wallet"]["game_balance_cents"], first_spin.data["wallet"]["provider_balance"])

    def test_disabled_game_allows_withdrawal_and_exact_transfer_retry(self):
        self.client.post("/api/v1/demo/payments/", {
            "client_key": "disabled-fund", "amount_cents": 1999, "method": "cash_app",
        }, format="json")
        transfer_data = {
            "client_key": "disabled-transfer", "direction": "to_game",
            "amount_cents": 1000, "game_slug": self.game.slug,
        }
        first = self.client.post("/api/v1/demo/transfers/", transfer_data, format="json")
        self.game.is_active = False
        self.game.save(update_fields=["is_active"])
        replay = self.client.post("/api/v1/demo/transfers/", transfer_data, format="json")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["wallet"]["game_balance_cents"], first.data["wallet"]["game_balance_cents"])
        listing = self.client.get("/api/v1/demo/game-balances/")
        selected = next(item for item in listing.data if item["slug"] == self.game.slug)
        self.assertFalse(selected["is_active"])
        self.assertEqual(selected["balance_cents"], 1000)
        other = self.other
        self.client.force_authenticate(user=other)
        other_listing = self.client.get("/api/v1/demo/game-balances/")
        self.assertEqual(next(item for item in other_listing.data if item["slug"] == self.game.slug)["balance_cents"], 0)
        self.client.force_authenticate(user=self.user)
        transfer_data["client_key"] = "disabled-withdrawal"
        transfer_data["direction"] = "from_game"
        withdrawal = self.client.post("/api/v1/demo/transfers/", transfer_data, format="json")
        self.assertEqual(withdrawal.status_code, 200)
        self.assertEqual(withdrawal.data["wallet"]["game_balance_cents"], 0)

    def test_fake_ledger_is_hidden_outside_demo_mode(self):
        self.client.post("/api/v1/demo/payments/", {
            "client_key": "isolation", "amount_cents": 999, "method": "cash_app", "simulate": "succeeded",
        }, format="json")
        with override_settings(DEMO_MODE=False):
            wallet = self.client.get("/api/v1/wallet/")
            history = self.client.get("/api/v1/wallet/transactions/")
        self.assertEqual(wallet.data["available_cents"], 0)
        self.assertEqual(history.data, [])
