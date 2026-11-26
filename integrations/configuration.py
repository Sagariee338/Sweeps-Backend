"""Environment-backed provider configuration; never log secret values."""
import os
import re
from dataclasses import dataclass
from cryptography.fernet import Fernet
from .game_clients.common.validation import https_url


@dataclass(frozen=True)
class ProviderConfigStatus:
    code: str
    required: tuple[str, ...]
    missing: tuple[str, ...]
    invalid: tuple[str, ...] = ()

    @property
    def configured(self):
        return not self.missing and not self.invalid


REQUIRED = {
    "firekirin": ("FIREKIRIN_AGENT_NAME", "FIREKIRIN_AGENT_PASSWORD_MD5", "PROVIDER_CREDENTIAL_KEY"),
    "orion": ("ORION_AGENT_NAME", "ORION_AGENT_PASSWORD_MD5", "PROVIDER_CREDENTIAL_KEY"),
    "fastapi": ("FASTAPI_BASE_URL", "FASTAPI_APP_ID", "FASTAPI_APP_SECRET", "PROVIDER_CREDENTIAL_KEY"),
    "gamevault": ("GAMEVAULT_BASE_URL", "GAMEVAULT_AGENT_ID", "GAMEVAULT_SECRET_KEY", "PROVIDER_CREDENTIAL_KEY"),
    "juwa2": ("JUWA2_BASE_URL", "JUWA2_AGENT_ID", "JUWA2_SECRET_KEY", "PROVIDER_CREDENTIAL_KEY"),
    "juwa2_free": ("JUWA2_FREE_BASE_URL", "JUWA2_FREE_AGENT_ID", "JUWA2_FREE_SECRET_KEY", "PROVIDER_CREDENTIAL_KEY"),
    "gameroom": ("GAMEROOM_BASE_URL", "GAMEROOM_AGENT_USERNAME", "GAMEROOM_AGENT_PASSWORD", "PROVIDER_CREDENTIAL_KEY"),
    "dollarpay": ("DOLLARPAY_MERCHANT_ID", "DOLLARPAY_MERCHANT_KEY"),
}


def provider_status(code, environ=None):
    values = os.environ if environ is None else environ
    names = REQUIRED[code]
    missing = tuple(name for name in names if not values.get(name) and not (
        name == "PROVIDER_CREDENTIAL_KEY" and values.get("FIREKIRIN_STATE_KEY")
    ))
    invalid = []
    key = values.get("PROVIDER_CREDENTIAL_KEY") or values.get("FIREKIRIN_STATE_KEY")
    if code != "dollarpay" and key:
        try:
            Fernet(key.encode("ascii"))
        except (ValueError, TypeError, UnicodeError):
            invalid.append("PROVIDER_CREDENTIAL_KEY" if values.get("PROVIDER_CREDENTIAL_KEY") else "FIREKIRIN_STATE_KEY")
    for name, origin_only in (
        ("DOLLARPAY_API_URL", True), ("FIREKIRIN_API_URL", False), ("ORION_API_URL", False),
        ("JUWA2_FREE_BASE_URL", True), ("JUWA2_BASE_URL", True), ("FASTAPI_BASE_URL", True), ("GAMEVAULT_BASE_URL", True), ("GAMEROOM_BASE_URL", True),
    ):
        if name in names or name.startswith(code.upper() + "_"):
            value = values.get(name)
            if value:
                try:
                    https_url(value, origin_only=origin_only)
                except ValueError:
                    invalid.append(name)
    for name in ("FIREKIRIN_AGENT_PASSWORD_MD5", "ORION_AGENT_PASSWORD_MD5"):
        if name in names and values.get(name) and not re.fullmatch(r"[0-9a-fA-F]{32}", values[name]):
            invalid.append(name)
    for prefix in ("GAMEVAULT", "JUWA2", "JUWA2_FREE"):
        name = f"{prefix}_AGENT_ID"
        if code == prefix.lower() and values.get(name) and not values[name].isdigit():
            invalid.append(name)
    if code == "dollarpay" and values.get("DOLLARPAY_TENANT_DOMAIN") and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", values["DOLLARPAY_TENANT_DOMAIN"]):
        invalid.append("DOLLARPAY_TENANT_DOMAIN")
    return ProviderConfigStatus(code=code, required=names, missing=missing, invalid=tuple(invalid))
