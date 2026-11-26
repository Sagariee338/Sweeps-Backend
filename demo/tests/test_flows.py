"""End-to-end local fake-money flow."""
from .base import DemoApiTestCase


class DemoApiTests(DemoApiTestCase):
    def test_fake_money_game_and_redemption_flow(self):
        paid = self.client.post("/api/v1/demo/payments/", {
            "client_key": "pay-1", "amount_cents": 1999, "method": "cash_app",
            "simulate": "succeeded",
        }, format="json")
        self.assertEqual(paid.status_code, 201)
        self.assertEqual(paid.data["wallet"]["available_cents"], 1999)
        repeat = self.client.post("/api/v1/demo/payments/", {
            "client_key": "pay-1", "amount_cents": 1999, "method": "cash_app",
            "simulate": "succeeded",
        }, format="json")
        self.assertEqual(repeat.data["wallet"]["available_cents"], 1999)
        transfer = self.client.post("/api/v1/demo/transfers/", {
            "client_key": "transfer-1", "direction": "to_game",
            "amount_cents": 1000, "game_slug": "test-reels",
        }, format="json")
        self.assertEqual(transfer.status_code, 200)
        self.assertEqual(transfer.data["wallet"]["provider_balance"], 1000)
        launch = self.client.post("/api/v1/demo/games/test-reels/launch/", {}, format="json")
        self.assertEqual(launch.status_code, 201)
        spin = self.client.post("/api/v1/demo/games/test-reels/spin/", {
            "session_id": launch.data["session_id"], "client_key": "spin-1", "stake_cents": 100,
        }, format="json")
        self.assertEqual(spin.status_code, 201)
        self.assertEqual(len(spin.data["round"]["symbols"]), 3)
        redeem = self.client.post("/api/v1/demo/redemptions/", {
            "client_key": "redeem-1", "amount_cents": 500, "method": "paypal",
            "recipient": "test@example.com", "simulate": "paid",
        }, format="json")
        self.assertEqual(redeem.status_code, 201)
        self.assertEqual(redeem.data["wallet"]["available_cents"], 499)
        self.assertNotIn("test@example.com", str(redeem.data))
