from __future__ import annotations

from paddle_cli import cli


def test_default_command_runs_one_shot_key_check(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_key_check", lambda: 7)
    monkeypatch.setattr(
        cli,
        "run_interactive",
        lambda _: (_ for _ in ()).throw(AssertionError("navigator should not start")),
    )

    assert cli.main([]) == 7


def test_interactive_subcommand_keeps_api_navigator(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_key_check", lambda: 7)
    monkeypatch.setattr(cli, "run_interactive", lambda _: 3)

    assert cli.main(["interactive"]) == 3
