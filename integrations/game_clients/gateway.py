"""Translate provider-specific game APIs into account lifecycle operations.

This module owns vendor selection and request shapes. The provider_accounts app
owns player permissions, durable state, audits, and balance snapshots.
"""
import hashlib
import os
import re
import secrets
import string

from provider_accounts.models import ProviderConnection

from django.core.exceptions import ImproperlyConfigured
from .common.credentials import decrypt, require_key
from .common.errors import ProviderClientError
from .fastapi.client import FastApiClient
from .firekirin.client import FireKirinClient, FireKirinUnavailable
from .gamevault.client import GameVaultClient
from .orion.client import OrionClient
from .juwa2.client import Juwa2Client


SUPPORTED = {
    ProviderConnection.Adapter.FIREKIRIN, ProviderConnection.Adapter.ORION,
    ProviderConnection.Adapter.FASTAPI, ProviderConnection.Adapter.GAMEVAULT, ProviderConnection.Adapter.JUWA2,
}
LAUNCHABLE = {ProviderConnection.Adapter.FIREKIRIN, ProviderConnection.Adapter.ORION}
HASHED_PASSWORD = {ProviderConnection.Adapter.FIREKIRIN, ProviderConnection.Adapter.ORION}


class ProviderConfigurationError(Exception):
    pass


def adapter_matches(connection):
    return connection.adapter == connection.provider.code and connection.adapter in SUPPORTED


def _secret(connection, default_name):
    name = connection.agent_password_env or default_name
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        raise ProviderConfigurationError("Invalid provider secret reference")
    return os.environ.get(name, "")


def client_for(connection, injected=None):
    if not adapter_matches(connection):
        raise ProviderConfigurationError("Provider and adapter do not match")
    try:
        require_key()
    except ImproperlyConfigured as error:
        raise ProviderConfigurationError("Provider credential encryption is unavailable") from error
    if injected is not None:
        if connection.adapter in HASHED_PASSWORD and injected.agent_name != connection.agent_name:
            raise ProviderConfigurationError("Provider connection does not match the configured agent")
        return injected
    adapter = connection.adapter
    try:
        if adapter == ProviderConnection.Adapter.FASTAPI:
            if os.environ.get("FASTAPI_APP_ID") != connection.agent_name:
                raise ProviderConfigurationError("FastAPI app ID does not match the connection")
            return FastApiClient(
                base_url=os.environ.get("FASTAPI_BASE_URL", ""), appid=connection.agent_name,
                appsecret=_secret(connection, "FASTAPI_APP_SECRET"),
            )
        if adapter == ProviderConnection.Adapter.JUWA2:
            if connection.environment == "mock":
                from .juwa2.mock import mock_client
                return mock_client(connection)
            shared = connection.mode == ProviderConnection.Mode.FREE_PLAY and connection.agent_password_env == "JUWA2_SECRET_KEY"
            if shared and os.environ.get("JUWA2_SHARED_AGENT_ACCOUNTS") != "1":
                raise ProviderConfigurationError("Shared-agent identity setup is not enabled")
            prefix = "JUWA2_FREE" if connection.mode == ProviderConnection.Mode.FREE_PLAY and not shared else "JUWA2"
            if os.environ.get(f"{prefix}_AGENT_ID") != connection.agent_name:
                raise ProviderConfigurationError("Juwa2 mode needs its own configured agent ID")
            return Juwa2Client(
                base_url=os.environ.get(f"{prefix}_BASE_URL", "https://apiinterface.juwa2.xin"),
                agent_id=connection.agent_name, secret_key=_secret(connection, f"{prefix}_SECRET_KEY"),
            )
        if adapter == ProviderConnection.Adapter.GAMEVAULT:
            if os.environ.get("GAMEVAULT_AGENT_ID") != connection.agent_name:
                raise ProviderConfigurationError("GameVault agent ID does not match the connection")
            return GameVaultClient(
                base_url=os.environ.get("GAMEVAULT_BASE_URL", ""), agent_id=connection.agent_name,
                secret_key=_secret(connection, "GAMEVAULT_SECRET_KEY"),
            )
        prefix = "ORION" if adapter == ProviderConnection.Adapter.ORION else "FIREKIRIN"
        if not connection.agent_password_env and os.environ.get(f"{prefix}_AGENT_NAME") != connection.agent_name:
            raise ProviderConfigurationError("Provider connection needs its own agent secret reference")
        cls = OrionClient if adapter == ProviderConnection.Adapter.ORION else FireKirinClient
        return cls(agent_name=connection.agent_name, agent_password_md5=_secret(connection, f"{prefix}_AGENT_PASSWORD_MD5"))
    except (ValueError, ProviderClientError) as error:
        raise ProviderConfigurationError("Provider credentials are incomplete or invalid") from error


def new_credentials(adapter):
    length = 12 if adapter == ProviderConnection.Adapter.FASTAPI else 24
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(length - 2)) + "A1"
    name_length = 14 if adapter == ProviderConnection.Adapter.FASTAPI else 30
    account_name = "ls" + secrets.token_hex(name_length // 2)
    return account_name, password, hashlib.md5(password.encode("utf-8")).hexdigest()


def register(client, connection, account, password, password_md5):
    adapter = connection.adapter
    if adapter in HASHED_PASSWORD:
        return client.register_user(account.external_account, password_md5)
    if adapter == ProviderConnection.Adapter.FASTAPI:
        return client.create_player(requestid=account.id.hex, account=account.external_account, password=password)
    if adapter in {ProviderConnection.Adapter.GAMEVAULT, ProviderConnection.Adapter.JUWA2}:
        return client.create_player(account=account.external_account, password=password)
    raise ProviderConfigurationError("Provider account API is unavailable")


def lookup(client, connection, account):
    adapter = connection.adapter
    if adapter in HASHED_PASSWORD:
        return client.query_info(account.external_account, decrypt(account.encrypted_password_md5))
    if adapter == ProviderConnection.Adapter.FASTAPI:
        return client.balance(requestid=secrets.token_hex(16), account=account.external_account)
    if adapter in {ProviderConnection.Adapter.GAMEVAULT, ProviderConnection.Adapter.JUWA2}:
        return client.player_id(account=account.external_account)
    raise ProviderConfigurationError("Provider lookup API is unavailable")


def external_id(connection, details):
    if not isinstance(details, dict):
        return ""
    key = {"firekirin": "gameId", "orion": "gameId", "fastapi": "full_account", "gamevault": "user_id", "juwa2": "user_id"}[connection.adapter]
    value = details.get(key)
    if value is None or isinstance(value, (bool, dict, list)):
        return ""
    identifier = str(value)
    if not identifier or len(identifier) > 80:
        return ""
    if connection.adapter in {ProviderConnection.Adapter.GAMEVAULT, ProviderConnection.Adapter.JUWA2} and not identifier.isdigit():
        return ""
    return identifier


def identity_ready(connection, details, existing_id=""):
    if not isinstance(details, dict):
        return False
    if connection.adapter in {ProviderConnection.Adapter.FASTAPI, ProviderConnection.Adapter.GAMEVAULT, ProviderConnection.Adapter.JUWA2}:
        return bool(external_id(connection, details) or existing_id)
    return True


def balance(client, connection, account):
    adapter = connection.adapter
    if adapter in HASHED_PASSWORD:
        details = client.query_info(account.external_account, decrypt(account.encrypted_password_md5))
        return details.get("userbalance"), "queryInfo"
    if adapter == ProviderConnection.Adapter.FASTAPI:
        details = client.balance(requestid=secrets.token_hex(16), account=account.external_account)
        return details.get("balance"), "balance"
    if adapter in {ProviderConnection.Adapter.GAMEVAULT, ProviderConnection.Adapter.JUWA2}:
        if not account.external_player_id:
            raise ProviderConfigurationError("Provider player ID needs reconciliation")
        details = client.player_balance(user_id=account.external_player_id)
        return details.get("user_balance"), "userBalance"
    raise ProviderConfigurationError("Provider balance API is unavailable")


def launch_url(client, connection, account, game):
    if connection.adapter == ProviderConnection.Adapter.ORION:
        return client.web_login(account.external_account)
    if connection.adapter == ProviderConnection.Adapter.FIREKIRIN:
        payload = client.enter_game(account.external_account, decrypt(account.encrypted_password_md5), game.external_id)
        url = payload.get("webLoginUrl")
        if url:
            return url
        raise FireKirinUnavailable("Provider did not return a launch URL")
    raise ProviderConfigurationError("Provider launch API is not documented")


def credential_username(account):
    if account.connection.adapter == ProviderConnection.Adapter.FASTAPI and account.external_player_id:
        return account.external_player_id
    return account.external_account
