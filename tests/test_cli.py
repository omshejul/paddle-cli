from __future__ import annotations

from paddle_cli import cli
from paddle_cli.client import KeyInfo, ResponseResult
from paddle_cli.credentials import StoredCredential


def test_default_command_runs_one_shot_key_check(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_key_check", lambda _: 7)
    monkeypatch.setattr(
        cli,
        "run_interactive",
        lambda *_: (_ for _ in ()).throw(AssertionError("navigator should not start")),
    )

    assert cli.main([]) == 7


def test_interactive_subcommand_keeps_api_navigator(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_key_check", lambda _: 7)
    monkeypatch.setattr(cli, "run_interactive", lambda *_: 3)

    assert cli.main(["interactive"]) == 3


def test_auth_login_forces_a_new_key_prompt(monkeypatch) -> None:
    seen: dict[str, bool] = {}

    def login(_, *, force_prompt: bool = False) -> int:
        seen["force_prompt"] = force_prompt
        return 4

    monkeypatch.setattr(cli, "run_key_check", login)

    assert cli.main(["auth", "login"]) == 4
    assert seen == {"force_prompt": True}


def test_logout_removes_saved_key() -> None:
    class Store:
        def delete(self) -> bool:
            return True

    assert cli._logout(Store()) == 0


def test_direct_request_reuses_saved_key(monkeypatch) -> None:
    api_key = "pdl_sdbx_apikey_saved"

    class Store:
        def load(self) -> StoredCredential:
            return StoredCredential(api_key, "sandbox")

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
