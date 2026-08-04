from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from paddle_cli import cli
from paddle_cli.client import KeyInfo, ResponseResult
from paddle_cli.credentials import ResolvedCredential


def test_default_command_shows_help_without_authentication(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "run_login",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("login should not start")),
    )

    assert cli.main([]) == 0
    output = capsys.readouterr().out
    assert "paddle login" in output
    assert "paddle interactive" in output


def test_interactive_subcommand_keeps_api_navigator(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_interactive", lambda *_args, **_kwargs: 3)

    assert cli.main(["interactive"]) == 3


def test_login_is_an_explicit_top_level_command(monkeypatch) -> None:
    seen: dict[str, str | None] = {}

    def login(
        _,
        *,
        api_key: str | None = None,
        environment: str | None = None,
        prompt_for_skill: bool = False,
    ) -> int:
        seen["api_key"] = api_key
        seen["environment"] = environment
        seen["prompt_for_skill"] = str(prompt_for_skill)
        return 4

    monkeypatch.setattr(cli, "run_login", login)

    assert cli.main(["login", "--key", "pdl_sdbx_apikey_test"]) == 4
    assert seen == {
        "api_key": "pdl_sdbx_apikey_test",
        "environment": None,
        "prompt_for_skill": "False",
    }


def test_login_can_read_key_from_standard_input(monkeypatch) -> None:
    seen: dict[str, str | None] = {}

    def login(
        _,
        *,
        api_key: str | None = None,
        environment: str | None = None,
        prompt_for_skill: bool = False,
    ) -> int:
        seen["api_key"] = api_key
        seen["environment"] = environment
        seen["prompt_for_skill"] = str(prompt_for_skill)
        return 0

    monkeypatch.setattr(cli, "run_login", login)
    monkeypatch.setattr(cli.sys, "stdin", StringIO("pdl_sdbx_apikey_stdin\n"))

    assert cli.main(["login", "--key-stdin"]) == 0
    assert seen == {
        "api_key": "pdl_sdbx_apikey_stdin",
        "environment": None,
        "prompt_for_skill": "False",
    }


def test_interactive_login_offers_agent_skill_install(monkeypatch) -> None:
    class InteractiveInput(StringIO):
        def isatty(self) -> bool:
            return True

    seen: dict[str, object] = {}

    def login(
        _,
        *,
        api_key: str | None = None,
        environment: str | None = None,
        prompt_for_skill: bool = False,
    ) -> int:
        seen.update(
            api_key=api_key,
            environment=environment,
            prompt_for_skill=prompt_for_skill,
        )
        return 0

    monkeypatch.setattr(cli, "run_login", login)
    monkeypatch.setattr(cli.sys, "stdin", InteractiveInput())

    assert cli.main(["login"]) == 0
    assert seen == {"api_key": None, "environment": None, "prompt_for_skill": True}


def test_skill_install_is_an_explicit_command(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_skill_install", lambda: 5)

    assert cli.main(["skill", "install"]) == 5


def test_old_nested_auth_command_is_not_exposed() -> None:
    with pytest.raises(SystemExit, match="2"):
        cli.build_parser().parse_args(["auth", "login"])


def test_logout_removes_saved_key() -> None:
    class Store:
        def delete(self) -> bool:
            return True

        def backend_name(self) -> str:
            return "Test Keychain"

    assert cli._logout(Store()) == 0


def test_logout_warns_when_environment_override_remains(monkeypatch) -> None:
    output = StringIO()

    class Store:
        def delete(self) -> bool:
            return False

    monkeypatch.setenv("PADDLE_API_KEY", "pdl_sdbx_apikey_environment")
    monkeypatch.setattr(cli, "console", Console(file=output, color_system=None))

    assert cli._logout(Store()) == 0
    assert "still set" in output.getvalue()


def test_config_remains_available_without_secure_backend(monkeypatch) -> None:
    output = StringIO()

    class Store:
        def backend_name(self) -> str:
            return "keyring.backends.null"

        def load(self) -> None:
            from paddle_cli.credentials import CredentialError

            raise CredentialError("unavailable")

    monkeypatch.setattr(cli, "console", Console(file=output, color_system=None, width=60))

    assert cli._show_config(Store()) == 0
    rendered = output.getvalue()
    assert "Unavailable" in rendered
    assert str(cli.default_cache_path()) in rendered


def test_direct_request_reuses_saved_key(monkeypatch) -> None:
    api_key = "pdl_sdbx_apikey_saved"

    class Store:
        def resolve(self, environment: str | None = None) -> ResolvedCredential:
            return ResolvedCredential(api_key, environment or "sandbox", "test")

    class FakeClient:
        key_info = KeyInfo("sandbox", True)

        def __init__(self, received_key: str, *, environment: str | None = None) -> None:
            assert received_key == api_key
            assert environment == "sandbox"

        def request(self, *_, **__) -> ResponseResult:
            return ResponseResult(200, "OK", {}, "req_123", 2)

    monkeypatch.delenv("PADDLE_API_KEY", raising=False)
    monkeypatch.setattr(cli, "PaddleClient", FakeClient)
    monkeypatch.setattr(cli, "render_response", lambda _: None)
    args = cli.build_parser().parse_args(["request", "GET", "/products"])

    assert cli._request(args, Store()) == 0


def test_unknown_help_topic_renders_without_traceback(monkeypatch) -> None:
    errors = StringIO()
    monkeypatch.setattr(cli, "error_console", Console(file=errors, color_system=None))

    assert cli.main(["help", "not-a-command"]) == 2
    assert errors.getvalue().strip() == "Unknown command: not-a-command"


def test_cli_error_renders_without_traceback(monkeypatch) -> None:
    errors = StringIO()
    monkeypatch.setattr(cli, "error_console", Console(file=errors, color_system=None))
    monkeypatch.setattr(
        cli,
        "_request",
        lambda *_: (_ for _ in ()).throw(ValueError("query must be a JSON object.")),
    )

    assert cli.main(["request", "GET", "/products"]) == 1
    assert errors.getvalue().strip() == "Error: query must be a JSON object."
