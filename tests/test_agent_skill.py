from __future__ import annotations

import json
from pathlib import Path

from paddle_cli import agent_skill
from paddle_cli.agent_skill import MANAGED_FILE, SHARED_AGENTS, ensure_agent_skills


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


def test_installs_one_shared_skill_and_links_claude_code(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    shared = home / ".agents" / "skills" / "paddle-cli"
    claude = home / ".claude" / "skills" / "paddle-cli"
    assert [item.agent for item in installed] == [SHARED_AGENTS, "Claude Code"]
    assert (shared / "SKILL.md").read_text(encoding="utf-8") == "skill v1"
    assert (shared / "agents" / "openai.yaml").read_text(encoding="utf-8") == "metadata v1"
    marker = json.loads((shared / MANAGED_FILE).read_text(encoding="utf-8"))
    assert len(marker["content_sha256"]) == 64
    assert claude.is_symlink()
    assert claude.resolve() == shared.resolve()

    assert ensure_agent_skills(home=home, environ={}, resource_root=bundle) == []


def test_uses_shared_agent_directory_even_with_custom_codex_home(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    custom_codex_home = tmp_path / "custom-codex"

    installed = ensure_agent_skills(
        home=home,
        environ={"CODEX_HOME": str(custom_codex_home)},
        resource_root=bundle,
    )

    assert len(installed) == 1
    assert installed[0].path == home / ".agents" / "skills" / "paddle-cli"
    assert not (custom_codex_home / "skills" / "paddle-cli").exists()


def test_does_not_remove_shared_skill_when_codex_home_is_agents_directory(
    tmp_path: Path,
) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    shared_root = home / ".agents"

    installed = ensure_agent_skills(
        home=home,
        environ={"CODEX_HOME": str(shared_root)},
        resource_root=bundle,
    )

    shared = shared_root / "skills" / "paddle-cli"
    assert [item.path for item in installed] == [shared]
    assert (shared / "SKILL.md").read_text(encoding="utf-8") == "skill v1"


def test_installs_shared_skill_without_detected_agents(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert [item.agent for item in installed] == [SHARED_AGENTS]
    assert installed[0].path == home / ".agents" / "skills" / "paddle-cli"


def test_falls_back_to_a_claude_copy_when_symlinks_are_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    def reject_symlink(*_args, **_kwargs) -> None:
        raise OSError("symlinks unavailable")

    monkeypatch.setattr(Path, "symlink_to", reject_symlink)

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    claude = home / ".claude" / "skills" / "paddle-cli"
    assert [item.agent for item in installed] == [SHARED_AGENTS, "Claude Code"]
    assert not claude.is_symlink()
    assert (claude / "SKILL.md").read_text(encoding="utf-8") == "skill v1"


def test_updates_an_unmodified_managed_skill(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    target = home / ".agents" / "skills" / "paddle-cli"
    ensure_agent_skills(home=home, environ={}, resource_root=bundle)
    (bundle / "SKILL.md").write_text("skill v2", encoding="utf-8")

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert [item.path for item in installed] == [target]
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "skill v2"


def test_preserves_a_user_modified_managed_skill(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    target = home / ".agents" / "skills" / "paddle-cli"
    ensure_agent_skills(home=home, environ={}, resource_root=bundle)
    (target / "SKILL.md").write_text("my custom skill", encoding="utf-8")
    (bundle / "SKILL.md").write_text("skill v2", encoding="utf-8")

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert installed == []
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "my custom skill"


def test_preserves_an_unmanaged_existing_skill(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    target = home / ".agents" / "skills" / "paddle-cli"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("someone else's skill", encoding="utf-8")

    installed = ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert installed == []
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "someone else's skill"


def test_migrates_an_unmodified_legacy_copy_to_the_shared_location(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    legacy = home / ".codex" / "skills" / "paddle-cli"
    contents = agent_skill._read_bundle(bundle)
    agent_skill._install_skill(legacy, contents)

    ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert not legacy.exists()
    assert (home / ".agents" / "skills" / "paddle-cli" / "SKILL.md").exists()


def test_preserves_a_modified_legacy_copy_during_migration(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path)
    home = tmp_path / "home"
    legacy = home / ".cursor" / "skills" / "paddle-cli"
    contents = agent_skill._read_bundle(bundle)
    agent_skill._install_skill(legacy, contents)
    (legacy / "notes.txt").write_text("keep me", encoding="utf-8")

    ensure_agent_skills(home=home, environ={}, resource_root=bundle)

    assert (legacy / "notes.txt").read_text(encoding="utf-8") == "keep me"
