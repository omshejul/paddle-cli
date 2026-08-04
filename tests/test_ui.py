from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from paddle_cli import ui
from paddle_cli.client import KeyInfo, ResponseResult
from paddle_cli.credentials import CredentialError, ResolvedCredential, StoredCredential
from paddle_cli.spec import Operation, PaddleSpec, Parameter
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
    assert "Configured" in rendered
    assert "paddle doctor" in rendered
    assert "system credential manager" in rendered
    assert "Test Keychain" in rendered


def test_whoami_requires_explicit_login_when_no_key_exists(monkeypatch) -> None:
    output = StringIO()
    monkeypatch.setattr(ui, "error_console", Console(file=output, color_system=None))

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

    monkeypatch.setattr(ui, "console", Console(file=StringIO(), color_system=None))
    monkeypatch.setattr(ui, "error_console", Console(file=output, color_system=None))
    monkeypatch.setattr(
        ui.inquirer,
        "secret",
        lambda **_: Prompt("pdl_sdbx_apikey_invalid"),
    )
    monkeypatch.setattr(ui, "PaddleClient", FakeClient)

    assert ui.run_login(store) == 1
    assert store.saved is None
    assert "API key is not valid" in output.getvalue()


def test_interactive_handles_credential_backend_errors(monkeypatch) -> None:
    output = StringIO()
    errors = StringIO()
    monkeypatch.setattr(ui, "console", Console(file=output, color_system=None))
    monkeypatch.setattr(ui, "error_console", Console(file=errors, color_system=None))
    monkeypatch.setattr(
        ui,
        "_authenticate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CredentialError("unavailable")),
    )

    assert ui.run_interactive(object(), object()) == 1
    assert "Error: unavailable" in errors.getvalue()


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


def test_search_returns_operation_instead_of_converted_dictionary(monkeypatch) -> None:
    operation = Operation("GET", "/event-types", "list-events", "List events", "", ("Events",))

    class Spec:
        def operations(self) -> list[Operation]:
            return [operation]

    monkeypatch.setattr(ui.inquirer, "text", lambda **_: Prompt("event"))

    def fuzzy(**kwargs) -> Prompt:
        choice = kwargs["choices"][0]
        assert isinstance(choice, dict)
        return Prompt(choice["value"])

    monkeypatch.setattr(ui.inquirer, "fuzzy", fuzzy)

    assert ui._search(Spec()) is operation


def test_browse_returns_operation_instead_of_converted_dictionary(monkeypatch) -> None:
    operation = Operation("GET", "/event-types", "list-events", "List events", "", ("Events",))
    answers = iter(["Events", operation])

    class Spec:
        def operations(self) -> list[Operation]:
            return [operation]

    def fuzzy(**kwargs) -> Prompt:
        if kwargs["message"] == "Operation:":
            assert isinstance(kwargs["choices"][0], dict)
        return Prompt(next(answers))

    monkeypatch.setattr(ui.inquirer, "fuzzy", fuzzy)

    assert ui._browse(Spec()) is operation


def test_optional_parameter_selection_preserves_parameter_type(monkeypatch) -> None:
    required = Parameter("customer_id", "path", True)
    optional = Parameter("include", "query", False, "Related entities")

    def checkbox(**kwargs) -> Prompt:
        choice = kwargs["choices"][0]
        assert isinstance(choice, dict)
        return Prompt([choice["value"]])

    monkeypatch.setattr(ui.inquirer, "checkbox", checkbox)

    assert ui._choose_parameters([required, optional]) == [required, optional]


class InteractiveClient:
    key_info = KeyInfo("sandbox", True)
    base_url = "https://sandbox-api.paddle.com"

    def __init__(self) -> None:
        self.operations: list[Operation] = []

    def request(self, operation: Operation, **_) -> ResponseResult:
        self.operations.append(operation)
        return ResponseResult(200, "OK", {"data": []}, "req_interactive", 5)


def interactive_spec() -> PaddleSpec:
    return PaddleSpec(
        {
            "openapi": "3.1.0",
            "paths": {
                "/event-types": {
                    "get": {
                        "operationId": "list-event-types",
                        "summary": "List event types",
                        "tags": ["Event types"],
                    }
                }
            },
        }
    )


def test_interactive_search_executes_read_and_returns_to_menu(monkeypatch) -> None:
    actions = iter(["search", "quit"])
    client = InteractiveClient()
    monkeypatch.setattr(ui, "console", Console(file=StringIO(), color_system=None))
    monkeypatch.setattr(ui.inquirer, "select", lambda **_: Prompt(next(actions)))
    monkeypatch.setattr(ui.inquirer, "text", lambda **_: Prompt("event types"))
    monkeypatch.setattr(
        ui.inquirer,
        "fuzzy",
        lambda **kwargs: Prompt(kwargs["choices"][0]["value"]),
    )

    assert ui._main_menu(interactive_spec(), client) == "quit"
    assert [operation.path for operation in client.operations] == ["/event-types"]


def test_interactive_browse_executes_read_and_returns_to_menu(monkeypatch) -> None:
    actions = iter(["browse", "quit"])
    client = InteractiveClient()
    monkeypatch.setattr(ui, "console", Console(file=StringIO(), color_system=None))
    monkeypatch.setattr(ui.inquirer, "select", lambda **_: Prompt(next(actions)))

    def fuzzy(**kwargs) -> Prompt:
        choice = kwargs["choices"][0]
        value = choice["value"] if isinstance(choice, dict) else choice.value
        return Prompt(value)

    monkeypatch.setattr(ui.inquirer, "fuzzy", fuzzy)

    assert ui._main_menu(interactive_spec(), client) == "quit"
    assert [operation.path for operation in client.operations] == ["/event-types"]


def test_interactive_raw_read_executes_and_returns_to_menu(monkeypatch) -> None:
    menu_actions = iter(["raw", "quit"])
    client = InteractiveClient()
    monkeypatch.setattr(ui, "console", Console(file=StringIO(), color_system=None))

    def select(**kwargs) -> Prompt:
        if kwargs["message"] == "HTTP method:":
            return Prompt("GET")
        return Prompt(next(menu_actions))

    def text_prompt(**kwargs) -> Prompt:
        if kwargs["message"] == "API path:":
            return Prompt("/event-types")
        return Prompt("")

    monkeypatch.setattr(ui.inquirer, "select", select)
    monkeypatch.setattr(ui.inquirer, "text", text_prompt)

    assert ui._main_menu(interactive_spec(), client) == "quit"
    assert [operation.path for operation in client.operations] == ["/event-types"]


def test_live_interactive_write_requires_exact_confirmation(monkeypatch) -> None:
    client = InteractiveClient()
    client.key_info = KeyInfo("live", True)
    client.base_url = "https://api.paddle.com"
    operation = Operation("POST", "/products", "create-product", "Create", "", ("Products",))
    monkeypatch.setattr(ui, "console", Console(file=StringIO(), color_system=None))
    monkeypatch.setattr(ui.inquirer, "text", lambda **_: Prompt("not LIVE"))

    ui._run_operation(interactive_spec(), client, operation)

    assert client.operations == []


def test_interactive_refresh_reloads_spec_before_returning_to_menu(monkeypatch) -> None:
    refreshes: list[bool] = []
    menu_results = iter(["refresh", "quit"])
    client = InteractiveClient()
    spec = interactive_spec()
    monkeypatch.setattr(ui, "console", Console(file=StringIO(), color_system=None))
    monkeypatch.setattr(ui, "_authenticate", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        ui,
        "_load_spec",
        lambda _store, refresh=False: refreshes.append(refresh) or spec,
    )
    monkeypatch.setattr(ui, "_main_menu", lambda *_: next(menu_results))

    assert ui.run_interactive(object(), object()) == 0
    assert refreshes == [False, True]
