from __future__ import annotations

import json
from pathlib import Path

from paddle_cli.agent_skill import MANAGED_FILE, agent_skill_targets, ensure_agent_skills


def make_bundle(root: Path, *, skill: str = "skill v1", metadata: str = "metadata v1") -> Path:
    bundle = root / "bundle"
    (bundle / "agents").mkdir(parents=True)
    (bundle / "SKILL.md").write_text(skill, encoding="utf-8")
    (bundle / "agents" / "openai.yaml").write_text(metadata, encoding="utf-8")
    return bundle


def test_bundled_skill_matches_the_public_repository_copy() -> None:
    repository = Path(__file__).parents[1]
    bundled = repository / "src" / "paddle_cli" / "bundled_skill"
    public = repository / "skills" / "paddle-cli"

    assert (bundled / "SKILL.md").read_text(encoding="utf-8") == (public / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert (bundled / "agents" / "openai.yaml").read_text(encoding="utf-8") == (
        public / "agents" / "openai.yaml"
    ).read_text(encoding="utf-8")


def test_installs_for_detected_agents_and_is_idempotent(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".claude").mkdir()

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert [item.agent for item in installed] == ["Codex", "Claude Code"]
    for item in installed:
        assert (item.path / "SKILL.md").read_text(encoding="utf-8") == "skill v1"
        assert (item.path / "agents" / "openai.yaml").read_text(encoding="utf-8") == (
            "metadata v1"
        )
        marker = json.loads((item.path / MANAGED_FILE).read_text(encoding="utf-8"))
        assert len(marker["content_sha256"]) == 64

    assert ensure_agent_skills(home=home, environ={}, resource_root=bundle) == []


def test_uses_codex_home_environment(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    custom_codex_home = tmp_path / "custom-codex"

    installed = ensure_agent_skills(
        home=tmp_path / "home",
        environ={"CODEX_HOME": str(custom_codex_home)},
        resource_root=bundle,
    )

    assert len(installed) == 1
    assert installed[0].path == custom_codex_home / "skills" / "paddle-cli"


def test_lists_detected_and_undetected_agents_for_selection(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)

    targets = agent_skill_targets(home=home, environ={})

    assert next(target for target in targets if target.agent == "Codex").detected is True
    assert next(target for target in targets if target.agent == "Cursor").detected is False


def test_installs_only_selected_agents(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"

    installed = ensure_agent_skills(
        agents=["Codex", "Cursor"],
        home=home,
        environ={},
        resource_root=bundle,
    )

    assert [item.agent for item in installed] == ["Codex", "Cursor"]
    assert not (home / ".claude" / "skills" / "paddle-cli").exists()


def test_falls_back_to_universal_agent_skills_directory(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert len(installed) == 1
    assert installed[0].path == home / ".config" / "agents" / "skills" / "paddle-cli"


def test_updates_an_unmodified_managed_skill(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    target = home / ".codex" / "skills" / "paddle-cli"
    ensure_agent_skills(home=home, environ={}, resource_root=bundle)
    (bundle / "SKILL.md").write_text("skill v2", encoding="utf-8")

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert [item.path for item in installed] == [target]
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "skill v2"


def test_preserves_a_user_modified_managed_skill(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    target = home / ".codex" / "skills" / "paddle-cli"
    ensure_agent_skills(home=home, environ={}, resource_root=bundle)
    (target / "SKILL.md").write_text("my custom skill", encoding="utf-8")
    (bundle / "SKILL.md").write_text("skill v2", encoding="utf-8")

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert installed == []
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "my custom skill"


def test_preserves_an_unmanaged_existing_skill(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    target = home / ".codex" / "skills" / "paddle-cli"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("someone else's skill", encoding="utf-8")

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert installed == []
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "someone else's skill"
