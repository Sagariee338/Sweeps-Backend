"""Juwa2 paid/free player identities; credit isolation is a separate capability."""
import os

from django.core.management.base import CommandError
from django.db import transaction

from catalog.models import Provider
from integrations.configuration import provider_status
from integrations.game_clients.common.validation import https_url
from provider_accounts.models import ProviderConnection


@transaction.atomic
def bootstrap_juwa2(stdout):
    paid_ready = provider_status("juwa2").configured
    free_id = os.environ.get("JUWA2_FREE_AGENT_ID", "")
    free_ready = provider_status("juwa2_free").configured
    if free_ready:
        try:
            https_url(os.environ.get("JUWA2_FREE_BASE_URL", "https://apiinterface.juwa2.xin"), origin_only=True)
        except ValueError as error:
            raise CommandError("Juwa2 free-play origin is invalid") from error
    paid_enabled = paid_ready and os.environ.get("JUWA2_VALUE_ACCOUNT_SETUP_APPROVED") == "1"
    if paid_enabled and os.environ.get("PROVIDER_VALUE_ACCOUNTS_ENABLED") != "1":
        raise CommandError("Juwa2 paid account setup also needs PROVIDER_VALUE_ACCOUNTS_ENABLED=1")
    isolated_free = free_ready and os.environ.get("JUWA2_FREE_PLAY_ISOLATED") == "1"
    if isolated_free and os.environ.get("PROVIDER_FREE_PLAY_ENABLED") != "1":
        raise CommandError("Juwa2 free play also needs PROVIDER_FREE_PLAY_ENABLED=1")
    if isolated_free and free_id == os.environ.get("JUWA2_AGENT_ID"):
        raise CommandError("Juwa2 paid and free-play modes require distinct operator agents")
    if not paid_ready and not free_ready:
        stdout.write("juwa2: skipped (real credentials incomplete)")
        return
    provider, _ = Provider.objects.get_or_create(code="juwa2", defaults={"name": "Juwa2", "is_active": False})
    shared = paid_ready and not free_ready and os.environ.get("JUWA2_SHARED_AGENT_ACCOUNTS") == "1"
    free_enabled = isolated_free or bool((shared or free_ready) and os.environ.get("PROVIDER_ACCOUNT_SETUP_ENABLED") == "1")
    for mode, prefix, enabled in [
        ("value_play", "JUWA2", paid_enabled), ("free_play", "JUWA2" if shared else "JUWA2_FREE", free_enabled),
    ]:
        code = f"juwa2-{'value' if mode == 'value_play' else 'free'}-env"
        desired = dict(provider=provider, environment="production", mode=mode, adapter="juwa2",
                       agent_name=os.environ.get(f"{prefix}_AGENT_ID", ""), agent_password_env=f"{prefix}_SECRET_KEY")
        connection, _ = ProviderConnection.objects.get_or_create(code=code, defaults=desired)
        changed = any(getattr(connection, key) != value for key, value in desired.items())
        if changed and connection.player_accounts.exists():
            raise CommandError("Existing Juwa2 identity has accounts; create a new connection for different credentials")
        for key, value in desired.items():
            setattr(connection, key, value)
        connection.is_enabled = connection.player_provisioning_enabled = enabled
        connection.mode_verified = bool(mode == "free_play" and isolated_free)
        connection.launch_enabled = False
        connection.save()
        stdout.write(f"juwa2/{mode}: account setup {'enabled' if enabled else 'unavailable'}; transfers disabled")
    if paid_enabled or free_enabled:
        provider.is_active = True
        provider.save(update_fields=["is_active"])
