from __future__ import annotations

import pytest

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

    def login(_, *, api_key: str | None = None, environment: str | None = None) -> int:
        seen["api_key"] = api_key
        seen["environment"] = environment
        return 4

    monkeypatch.setattr(cli, "run_login", login)

    assert cli.main(["login", "--key", "pdl_sdbx_apikey_test"]) == 4
    assert seen == {"api_key": "pdl_sdbx_apikey_test", "environment": None}


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
