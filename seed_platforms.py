from django.core.management.base import BaseCommand
from django.db import transaction
from catalog.models import Provider
from catalog.platforms import PLATFORMS


class Command(BaseCommand):
    help = "Create the selected real platform directory without enabling unknown APIs"

    @transaction.atomic
    def handle(self, *args, **options):
        for code, name in PLATFORMS.items():
            provider, _ = Provider.objects.get_or_create(code=code, defaults={"name": name})
            if provider.name != name:
                provider.name = name
                provider.save(update_fields=["name"])
        self.stdout.write(f"Selected platform directory ready: {len(PLATFORMS)} real platforms")
