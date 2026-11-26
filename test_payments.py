"""Fake payments and redemption idempotency and limits."""
from rest_framework.test import APIClient
from .base import DemoApiTestCase


class DemoApiTests(DemoApiTestCase):
    def test_payment_and_redemption_keys_reject_changed_request(self):
        payment = {"client_key": "same-payment", "amount_cents": 1999, "method": "cash_app", "simulate": "succeeded"}
        first = self.client.post("/api/v1/demo/payments/", payment, format="json")
        self.assertEqual(first.status_code, 201)
        changed_payment = {**payment, "simulate": "pending"}
        self.assertEqual(self.client.post("/api/v1/demo/payments/", changed_payment, format="json").status_code, 400)
        redemption = {
            "client_key": "same-redemption", "amount_cents": 500, "method": "paypal",
            "recipient": "first@example.com", "simulate": "pending",
        }
        first_redemption = self.client.post("/api/v1/demo/redemptions/", redemption, format="json")
        self.assertEqual(first_redemption.status_code, 201)
        changed_redemption = {**redemption, "recipient": "other@example.com"}
        self.assertEqual(self.client.post("/api/v1/demo/redemptions/", changed_redemption, format="json").status_code, 400)
        retry = self.client.post("/api/v1/demo/redemptions/", redemption, format="json")
        self.assertEqual(retry.data["redemption"]["id"], first_redemption.data["redemption"]["id"])

    def test_ownership_and_validation(self):
        unauthorized = APIClient().post("/api/v1/demo/payments/", {
            "client_key": "x", "amount_cents": 999, "method": "cash_app",
        }, format="json")
        self.assertEqual(unauthorized.status_code, 403)
        bad = self.client.post("/api/v1/demo/payments/", {
            "client_key": "x", "amount_cents": 1234, "method": "cash_app",
        }, format="json")
        self.assertEqual(bad.status_code, 400)
        pending = self.client.post("/api/v1/demo/payments/", {
            "client_key": "pending", "amount_cents": 999, "method": "cash_app", "simulate": "pending",
        }, format="json")
        self.client.force_authenticate(user=self.other)
        cross_user = self.client.post(
            f"/api/v1/demo/payments/{pending.data['payment']['id']}/resolve/",
            {"status": "succeeded"}, format="json",
        )
        self.assertEqual(cross_user.status_code, 400)

    def test_pending_resolution_and_refund(self):
        pending = self.client.post("/api/v1/demo/payments/", {
            "client_key": "pending-1", "amount_cents": 999, "method": "cash_app", "simulate": "pending",
        }, format="json")
        self.assertEqual(pending.data["wallet"]["available_cents"], 0)
        order_id = pending.data["payment"]["id"]
        success = self.client.post(
            f"/api/v1/demo/payments/{order_id}/resolve/", {"status": "succeeded"}, format="json"
        )
        self.assertEqual(success.data["wallet"]["available_cents"], 999)
        refunded = self.client.post(
            f"/api/v1/demo/payments/{order_id}/resolve/", {"status": "refunded"}, format="json"
        )
        self.assertEqual(refunded.data["wallet"]["available_cents"], 0)

    def test_daily_funding_limit_blocks_direct_and_pending_settlement(self):
        limit = self.client.post("/api/v1/auth/play-control/funding-limit/", {"amount_cents": 1000}, format="json")
        self.assertEqual(limit.status_code, 200)
        self.assertEqual(limit.data["daily_funding_limit_cents"], 1000)
        paid = self.client.post("/api/v1/demo/payments/", {
            "client_key": "within-limit", "amount_cents": 999, "method": "cash_app", "simulate": "succeeded",
        }, format="json")
        self.assertEqual(paid.status_code, 201)
        blocked = self.client.post("/api/v1/demo/payments/", {
            "client_key": "over-limit", "amount_cents": 499, "method": "cash_app", "simulate": "succeeded",
        }, format="json")
        self.assertEqual(blocked.status_code, 400)
        pending = self.client.post("/api/v1/demo/payments/", {
            "client_key": "pending-limit", "amount_cents": 499, "method": "cash_app", "simulate": "pending",
        }, format="json")
        self.assertEqual(pending.status_code, 201)
        settle = self.client.post(f"/api/v1/demo/payments/{pending.data['payment']['id']}/resolve/", {"status": "succeeded"}, format="json")
        self.assertEqual(settle.status_code, 400)
        raised = self.client.post("/api/v1/auth/play-control/funding-limit/", {"amount_cents": 2500}, format="json")
        self.assertEqual(raised.data["daily_funding_limit_cents"], 1000)
        self.assertEqual(raised.data["pending_daily_funding_limit_cents"], 2500)
