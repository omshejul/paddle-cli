from __future__ import annotations

import json

import pytest
from keyring.errors import KeyringError

from paddle_cli import credentials
from paddle_cli.credentials import (
    CredentialError,
    CredentialStore,
    ResolvedCredential,
    StoredCredential,
)


def test_system_store_round_trip(monkeypatch) -> None:
    values: dict[tuple[str, str], str] = {}

    monkeypatch.setattr(
        credentials.keyring,
        "get_password",
        lambda service, account: values.get((service, account)),
    )
    monkeypatch.setattr(
        credentials.keyring,
        "set_password",
        lambda service, account, value: values.__setitem__((service, account), value),
    )
    monkeypatch.setattr(
        credentials.keyring,
        "delete_password",
        lambda service, account: values.pop((service, account)),
    )
    store = CredentialStore()

    assert store.load() is None
    store.save("pdl_sdbx_apikey_secret", "sandbox")
    assert store.load() == StoredCredential("pdl_sdbx_apikey_secret", "sandbox")
    assert json.loads(values[(credentials.SERVICE_NAME, credentials.ACCOUNT_NAME)]) == {
        "api_key": "pdl_sdbx_apikey_secret",
        "environment": "sandbox",
    }
    assert store.delete() is True
    assert store.load() is None


def test_system_store_errors_do_not_include_secrets(monkeypatch) -> None:
    def fail(*_) -> None:
        raise KeyringError("backend failed")

    monkeypatch.setattr(credentials.keyring, "set_password", fail)

    with pytest.raises(CredentialError, match="Could not save") as error:
        CredentialStore().save("pdl_live_apikey_do-not-leak", "live")

    assert "do-not-leak" not in str(error.value)


def test_delete_removes_an_unreadable_saved_value(monkeypatch) -> None:
    values = {(credentials.SERVICE_NAME, credentials.ACCOUNT_NAME): "not-json"}
    monkeypatch.setattr(
        credentials.keyring,
        "get_password",
        lambda service, account: values.get((service, account)),
    )
    monkeypatch.setattr(
        credentials.keyring,
        "delete_password",
        lambda service, account: values.pop((service, account)),
    )

    assert CredentialStore().delete() is True
    assert values == {}


def test_environment_key_overrides_saved_key(monkeypatch) -> None:
    monkeypatch.setenv("PADDLE_API_KEY", "pdl_live_apikey_environment")
    monkeypatch.setattr(
        credentials.keyring,
        "get_password",
        lambda *_: (_ for _ in ()).throw(AssertionError("keychain should not be read")),
    )

    assert CredentialStore().resolve() == ResolvedCredential(
        "pdl_live_apikey_environment",
        None,
        "environment variable",
    )


def test_saved_key_is_used_when_environment_key_is_absent(monkeypatch) -> None:
    monkeypatch.delenv("PADDLE_API_KEY", raising=False)
    payload = json.dumps({"api_key": "pdl_sdbx_apikey_saved", "environment": "sandbox"})
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *_: payload)

    assert CredentialStore().resolve() == ResolvedCredential(
        "pdl_sdbx_apikey_saved",
        "sandbox",
        "system credential manager",
    )
