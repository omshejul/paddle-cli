from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from paddle_cli import ui
from paddle_cli.client import KeyInfo, ResponseResult
from paddle_cli.credentials import ResolvedCredential, StoredCredential
from paddle_cli.ui import pagination_query, parse_typed_value, shorten


class Prompt:
    def __init__(self, value: str) -> None:
        self.value = value

    def execute(self) -> str:
        return self.value


class MemoryStore:
    def __init__(self, credential: StoredCredential | None = None) -> None:
        self.credential = credential
        self.saved: tuple[str, str] | None = None

    def load(self) -> StoredCredential | None:
        return self.credential

    def save(self, api_key: str, environment: str) -> None:
        self.saved = (api_key, environment)

    def resolve(self, environment: str | None = None) -> ResolvedCredential | None:
        if self.credential is None:
            return None
        return ResolvedCredential(
            self.credential.api_key,
            environment or self.credential.environment,
            "system credential manager",
        )

    def backend_name(self) -> str:
        return "Test Keychain"


def test_login_validates_once_and_saves(monkeypatch) -> None:
    output = StringIO()
    calls = {"verify": 0}
    store = MemoryStore()
    api_key = "pdl_live_apikey_01gtgztp8f4kek3yd4g1wrksa3_q6TGTJyvoIz7LDtXT65bX7_AQO"

    class FakeClient:
        key_info = KeyInfo("live", True, "01gtgztp8f4kek3yd4g1wrksa3")
        base_url = "https://api.paddle.com"

        def __init__(self, received_key: str, *, environment: str | None = None) -> None:
            assert received_key == api_key
            assert environment is None

        def verify(self) -> ResponseResult:
            calls["verify"] += 1
            return ResponseResult(200, "OK", {}, "req_123", 5)

    monkeypatch.setattr(ui, "console", Console(file=output, color_system=None))
    monkeypatch.setattr(ui.inquirer, "secret", lambda **_: Prompt(api_key))
    monkeypatch.setattr(ui, "PaddleClient", FakeClient)

    assert ui.run_login(store) == 0
    assert calls["verify"] == 1
    assert store.saved == (api_key, "live")
    rendered = output.getvalue()
    assert "API key is valid" in rendered
    assert "Live" in rendered
    assert "apikey_01gtgztp8f4kek3yd4g1wrksa3" in rendered
    assert "API key saved" in rendered
    assert "paddle whoami" in rendered
    assert api_key not in rendered


def test_whoami_reads_saved_key_without_network_or_prompt(monkeypatch) -> None:
    output = StringIO()
    api_key = "pdl_sdbx_apikey_saved"
    store = MemoryStore(StoredCredential(api_key, "sandbox"))

    class FakeClient:
        key_info = KeyInfo("sandbox", True)
        base_url = "https://sandbox-api.paddle.com"

        def __init__(self, received_key: str, *, environment: str | None = None) -> None:
            assert received_key == api_key
            assert environment == "sandbox"

    monkeypatch.setattr(ui, "console", Console(file=output, color_system=None))
    monkeypatch.setattr(
        ui.inquirer,
        "secret",
        lambda **_: (_ for _ in ()).throw(AssertionError("key prompt should not open")),
    )
    monkeypatch.setattr(ui, "PaddleClient", FakeClient)

    assert ui.run_whoami(store) == 0
    assert store.saved is None
    rendered = output.getvalue()
    assert "Authenticated" in rendered
    assert "system credential manager" in rendered
    assert "Test Keychain" in rendered


def test_whoami_requires_explicit_login_when_no_key_exists(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(ui, "console", Console(file=output, color_system=None))

    assert ui.run_whoami(MemoryStore()) == 1
    assert "paddle login" in output.getvalue()


def test_doctor_performs_live_credential_check(monkeypatch) -> None:
    output = StringIO()
    calls = {"verify": 0}
    store = MemoryStore(StoredCredential("pdl_sdbx_apikey_saved", "sandbox"))

    class FakeClient:
        key_info = KeyInfo("sandbox", True)
        base_url = "https://sandbox-api.paddle.com"

        def __init__(self, received_key: str, *, environment: str | None = None) -> None:
            assert received_key == "pdl_sdbx_apikey_saved"
            assert environment == "sandbox"

        def verify(self) -> ResponseResult:
            calls["verify"] += 1
            return ResponseResult(200, "OK", {}, "req_123", 5)

    monkeypatch.setattr(ui, "console", Console(file=output, color_system=None))
    monkeypatch.setattr(ui, "PaddleClient", FakeClient)

    assert ui.run_doctor(store) == 0
    assert calls == {"verify": 1}
    assert "API key is valid" in output.getvalue()


def test_login_returns_failure_for_rejected_key(monkeypatch) -> None:
    output = StringIO()
    store = MemoryStore()

    class FakeClient:
        key_info = KeyInfo("sandbox", True)
        base_url = "https://sandbox-api.paddle.com"

        def __init__(self, received_key: str, *, environment: str | None = None) -> None:
            assert received_key == "pdl_sdbx_apikey_invalid"
            assert environment is None

        def verify(self) -> ResponseResult:
            return ResponseResult(403, "Forbidden", {}, "req_456", 5)

    monkeypatch.setattr(ui, "console", Console(file=output, color_system=None))
    monkeypatch.setattr(
        ui.inquirer,
        "secret",
        lambda **_: Prompt("pdl_sdbx_apikey_invalid"),
    )
    monkeypatch.setattr(ui, "PaddleClient", FakeClient)

    assert ui.run_login(store) == 1
    assert store.saved is None
    assert "API key is not valid" in output.getvalue()


def test_parse_typed_values() -> None:
    assert parse_typed_value("12", {"type": "integer"}) == 12
    assert parse_typed_value("1.5", {"type": "number"}) == 1.5
    assert parse_typed_value("yes", {"type": "boolean"}) is True
    assert parse_typed_value('["a","b"]', {"type": "array"}) == ["a", "b"]
    assert parse_typed_value('{"a":1}', {"type": "object"}) == {"a": 1}


def test_invalid_typed_value_has_actionable_error() -> None:
    with pytest.raises(ValueError, match="whole number"):
        parse_typed_value("abc", {"type": "integer"})


def test_pagination_query_reads_cursor() -> None:
    assert pagination_query("https://api.paddle.com/products?after=pro_123&per_page=20") == {
        "after": "pro_123",
        "per_page": "20",
    }


def test_shorten_normalizes_whitespace() -> None:
    assert shorten("one\n two", 20) == "one two"
    assert shorten("abcdefghijklmnopqrstuvwxyz", 10) == "abcdefghi…"
