"""Local rounds, sessions, choice rules, and replay."""
from datetime import timedelta
from django.utils import timezone
from catalog.models import Game
from demo.models import DemoGameRound, DemoGameSession
from wallet.models import LedgerTransaction
from .base import DemoApiTestCase


class DemoApiTests(DemoApiTestCase):
    def test_round_history_includes_free_rounds_and_is_owner_scoped(self):
        launch = self.client.post(f"/api/v1/demo/games/{self.game.slug}/launch/", {}, format="json")
        self.client.post(f"/api/v1/demo/games/{self.game.slug}/spin/", {
            "session_id": launch.data["session_id"], "client_key": "history-free-round", "stake_cents": 0,
        }, format="json")
        result = self.client.get("/api/v1/demo/rounds/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result["Cache-Control"], "no-store")
        self.assertEqual(len(result.data), 1)
        self.assertEqual(result.data[0]["game_slug"], self.game.slug)
        self.assertEqual(result.data[0]["stake_cents"], 0)
        self.assertEqual(LedgerTransaction.objects.count(), 0)
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.get("/api/v1/demo/rounds/").data, [])
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/v1/demo/rounds/").status_code, 403)

    def test_every_demo_category_can_play_for_free_without_funding(self):
        provider = self.game.provider
        for category, choice in (("slots", ""), ("fish", "reef"), ("arcade", "jade"), ("table", "red")):
            game = Game.objects.create(
                provider=provider, external_id=f"free-{category}", slug=f"free-{category}",
                title=f"Free {category}", category=category, is_active=True,
            )
            launch = self.client.post(f"/api/v1/demo/games/{game.slug}/launch/", {}, format="json")
            self.assertEqual(launch.status_code, 201)
            payload = {"session_id": launch.data["session_id"], "client_key": f"round-{category}", "stake_cents": 0}
            if choice:
                payload["choice"] = choice
            play = self.client.post(f"/api/v1/demo/games/{game.slug}/spin/", payload, format="json")
            self.assertEqual(play.status_code, 201)
            self.assertEqual(play.data["round"]["stake_cents"], 0)
            self.assertEqual(play.data["round"]["payout_cents"], 0)
            self.assertEqual(play.data["wallet"]["available_cents"], 0)
            self.assertEqual(play.data["wallet"]["provider_balance"], 0)
            repeat = self.client.post(f"/api/v1/demo/games/{game.slug}/spin/", payload, format="json")
            self.assertEqual(repeat.data["round"]["id"], play.data["round"]["id"])
            self.assertEqual(DemoGameRound.objects.filter(session_id=launch.data["session_id"]).count(), 1)
        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_category_choice_is_required_and_part_of_idempotency(self):
        game = Game.objects.create(
            provider=self.game.provider, external_id="free-fish-choice", slug="free-fish-choice",
            title="Fish choice", category="fish", is_active=True,
        )
        launch = self.client.post(f"/api/v1/demo/games/{game.slug}/launch/", {}, format="json")
        path = f"/api/v1/demo/games/{game.slug}/spin/"
        payload = {"session_id": launch.data["session_id"], "client_key": "fish-round", "stake_cents": 0}
        self.assertEqual(self.client.post(path, payload, format="json").status_code, 400)
        payload["choice"] = "reef"
        self.assertEqual(self.client.post(path, payload, format="json").status_code, 201)
        payload["choice"] = "deep"
        self.assertEqual(self.client.post(path, payload, format="json").status_code, 400)

    def test_legacy_fish_round_remains_replayable(self):
        game = Game.objects.create(
            provider=self.game.provider, external_id="legacy-fish", slug="legacy-fish",
            title="Legacy Fish", category="fish", is_active=True,
        )
        launch = self.client.post(f"/api/v1/demo/games/{game.slug}/launch/", {}, format="json")
        DemoGameRound.objects.create(
            session_id=launch.data["session_id"], client_key="legacy-round",
            stake_cents=0, payout_cents=0, symbols=["◆", "✦", "7"],
        )
        replay = self.client.post(f"/api/v1/demo/games/{game.slug}/spin/", {
            "session_id": launch.data["session_id"], "client_key": "legacy-round",
            "stake_cents": 0, "choice": "reef",
        }, format="json")
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(len(replay.data["round"]["symbols"]), 3)

    def test_game_session_is_owned_reused_and_expires(self):
        first = self.client.post("/api/v1/demo/games/test-reels/launch/", {}, format="json")
        again = self.client.post("/api/v1/demo/games/test-reels/launch/", {}, format="json")
        self.assertEqual(first.data["session_id"], again.data["session_id"])
        self.assertEqual(DemoGameSession.objects.filter(user=self.user, game=self.game).count(), 1)
        path = "/api/v1/demo/games/test-reels/spin/"
        payload = {"session_id": first.data["session_id"], "client_key": "owned-round", "stake_cents": 0}
        self.client.force_authenticate(user=self.other)
        self.assertEqual(self.client.post(path, payload, format="json").status_code, 400)
        self.client.force_authenticate(user=self.user)
        session = DemoGameSession.objects.get(pk=first.data["session_id"])
        session.expires_at = timezone.now() - timedelta(seconds=1)
        session.save(update_fields=["expires_at"])
        expired = self.client.post(path, payload, format="json")
        self.assertEqual(expired.status_code, 400)
        self.assertIn("expired", str(expired.data).lower())
        relaunched = self.client.post("/api/v1/demo/games/test-reels/launch/", {}, format="json")
        self.assertNotEqual(relaunched.data["session_id"], first.data["session_id"])
        payload["session_id"] = relaunched.data["session_id"]
        self.assertEqual(self.client.post(path, payload, format="json").status_code, 201)

    def test_disabling_game_stops_existing_session(self):
        launch = self.client.post("/api/v1/demo/games/test-reels/launch/", {}, format="json")
        self.game.is_active = False
        self.game.save(update_fields=["is_active"])
        result = self.client.post("/api/v1/demo/games/test-reels/spin/", {
            "session_id": launch.data["session_id"], "client_key": "disabled-round", "stake_cents": 0,
        }, format="json")
        self.assertEqual(result.status_code, 400)
        self.assertEqual(DemoGameRound.objects.count(), 0)

    def test_play_pause_stops_existing_session(self):
        launch = self.client.post("/api/v1/demo/games/test-reels/launch/", {}, format="json")
        pause = self.client.post("/api/v1/auth/play-control/", {"days": 1}, format="json")
        self.assertEqual(pause.status_code, 200)
        result = self.client.post("/api/v1/demo/games/test-reels/spin/", {
            "session_id": launch.data["session_id"], "client_key": "paused-round", "stake_cents": 0,
        }, format="json")
        self.assertEqual(result.status_code, 400)
        self.assertEqual(DemoGameRound.objects.count(), 0)

    def test_exact_round_retry_survives_play_pause(self):
        launch = self.client.post("/api/v1/demo/games/test-reels/launch/", {}, format="json")
        payload = {"session_id": launch.data["session_id"], "client_key": "round-before-pause", "stake_cents": 0}
        first = self.client.post("/api/v1/demo/games/test-reels/spin/", payload, format="json")
        self.client.post("/api/v1/auth/play-control/", {"days": 1}, format="json")
        replay = self.client.post("/api/v1/demo/games/test-reels/spin/", payload, format="json")
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.data["round"]["id"], first.data["round"]["id"])
        payload["client_key"] = "new-round-during-pause"
        self.assertEqual(self.client.post("/api/v1/demo/games/test-reels/spin/", payload, format="json").status_code, 400)
