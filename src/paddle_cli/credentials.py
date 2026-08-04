from __future__ import annotations

import json
from dataclasses import dataclass

import keyring
from keyring.errors import KeyringError

SERVICE_NAME = "paddle-api-cli"
ACCOUNT_NAME = "default"


class CredentialError(RuntimeError):
    """A safe error raised when system credential storage is unavailable."""


@dataclass(frozen=True)
class StoredCredential:
    api_key: str
    environment: str


class CredentialStore:
    def load(self) -> StoredCredential | None:
        try:
            raw = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
        except KeyringError as exc:
            raise CredentialError("Could not read the saved key from system credentials.") from exc
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CredentialError("The saved Paddle credential is unreadable.") from exc
        if not isinstance(payload, dict):
            raise CredentialError("The saved Paddle credential is unreadable.")
        api_key = payload.get("api_key")
        environment = payload.get("environment")
        if not isinstance(api_key, str) or environment not in {"sandbox", "live"}:
            raise CredentialError("The saved Paddle credential is unreadable.")
        return StoredCredential(api_key=api_key, environment=environment)

    def save(self, api_key: str, environment: str) -> None:
        payload = json.dumps(
            {"api_key": api_key, "environment": environment},
            separators=(",", ":"),
        )
        try:
            keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, payload)
        except KeyringError as exc:
            raise CredentialError("Could not save the key in system credentials.") from exc

    def delete(self) -> bool:
        try:
            existing = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
        except KeyringError as exc:
            raise CredentialError("Could not read the saved key from system credentials.") from exc
        if existing is None:
            return False
        try:
            keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
        except KeyringError as exc:
            raise CredentialError("Could not remove the key from system credentials.") from exc
        return True
