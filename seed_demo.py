from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from catalog.models import Game, Provider

DEMO_GAMES = [
    ("golden-tides", "Golden Tides", "fish", "An original ocean-themed test game."),
    ("royal-orbit", "Royal Orbit", "slots", "A celestial reel test game."),
    ("coral-quest", "Coral Quest", "fish", "A colorful fish test game."),
    ("lucky-lantern", "Lucky Lantern", "slots", "A lantern-inspired reel test game."),
    ("emerald-vault", "Emerald Vault", "arcade", "A gem-themed arcade test game."),
    ("midnight-seven", "Midnight Seven", "slots", "A classic reel test game."),
    ("pearl-parade", "Pearl Parade", "fish", "An underwater test game."),
    ("sunset-reels", "Sunset Reels", "slots", "A warm-toned reel test game."),
    ("jade-dynasty", "Jade Dynasty", "arcade", "A jade-themed arcade test game."),
    ("starlight-table", "Starlight Table", "table", "A table game test listing."),
    ("ruby-rush", "Ruby Rush", "slots", "A gem-themed reel test game."),
    ("ocean-crown", "Ocean Crown", "fish", "An ocean game test listing."),
]


class Command(BaseCommand):
    help = "Seed clearly labeled local demo games; never use for a live catalog"

    def handle(self, *args, **options):
        if not settings.DEMO_MODE:
            raise CommandError("seed_demo requires DJANGO_DEBUG=1 and DEMO_MODE=1")
        provider, _ = Provider.objects.update_or_create(
            code="demo", defaults={"name": "Local Demo", "is_active": True}
        )
        # The API document is available, but this is not an activated vendor.
        Provider.objects.get_or_create(
            code="firekirin", defaults={"name": "FireKirin", "is_active": False},
        )
        for slug, title, category, description in DEMO_GAMES:
            Game.objects.update_or_create(
                provider=provider, external_id=slug,
                defaults={
                    "slug": slug, "title": title, "category": category,
                    "description": description, "is_active": True,
                    "is_featured": slug in {"golden-tides", "royal-orbit", "lucky-lantern"},
                },
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(DEMO_GAMES)} local demo games"))
