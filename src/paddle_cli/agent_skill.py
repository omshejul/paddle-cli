from __future__ import annotations

import json
import os
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from paddle_cli import __version__

SKILL_NAME = "paddle-cli"
MANAGED_FILE = ".paddle-cli-managed.json"
BUNDLED_FILES = ("SKILL.md", "agents/openai.yaml")


@dataclass(frozen=True)
class SkillInstallation:
    agent: str
    path: Path


@dataclass(frozen=True)
class SkillTarget:
    agent: str
    path: Path
    detected: bool


def agent_skill_targets(
    *,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[SkillTarget]:
    """Return every supported agent target and whether it is present locally."""
    resolved_home = home or Path.home()
    resolved_environ = environ if environ is not None else os.environ
    return _agent_targets(resolved_home, resolved_environ)


def ensure_agent_skills(
    *,
    agents: Collection[str] | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    resource_root: Path | None = None,
) -> list[SkillInstallation]:
    """Install the bundled skill for selected or detected agents without replacing edits."""
    resolved_home = home or Path.home()
    resolved_environ = environ if environ is not None else os.environ
    resolved_resources = resource_root or Path(__file__).with_name("bundled_skill")
    try:
        contents = _read_bundle(resolved_resources)
    except OSError:
        return []

    targets = _agent_targets(resolved_home, resolved_environ)
    if agents is None:
        selected_targets = [target for target in targets if target.detected]
        if not selected_targets:
            selected_targets = [target for target in targets if target.agent == "Universal Agents"]
    else:
        selected_agents = set(agents)
        selected_targets = [target for target in targets if target.agent in selected_agents]

    installed: list[SkillInstallation] = []
    for selected in selected_targets:
        try:
            changed = _install_skill(selected.path, contents)
        except (OSError, ValueError):
            continue
        if changed:
            installed.append(SkillInstallation(selected.agent, selected.path))
    return installed


def _agent_targets(home: Path, environ: Mapping[str, str]) -> list[SkillTarget]:
    codex_home = Path(environ.get("CODEX_HOME", home / ".codex")).expanduser()
    candidates = (
        ("Codex", codex_home, bool(environ.get("CODEX_HOME")) or codex_home.exists()),
        ("Claude Code", home / ".claude", (home / ".claude").exists()),
        ("Cursor", home / ".cursor", (home / ".cursor").exists()),
        ("Gemini CLI", home / ".gemini", (home / ".gemini").exists()),
        ("GitHub Copilot", home / ".copilot", (home / ".copilot").exists()),
        ("OpenCode", home / ".config" / "opencode", (home / ".config" / "opencode").exists()),
        ("Agent Skills", home / ".agents", (home / ".agents").exists()),
        (
            "Universal Agents",
            home / ".config" / "agents",
            (home / ".config" / "agents").exists(),
        ),
    )
    return [
        SkillTarget(agent, root / "skills" / SKILL_NAME, detected)
        for agent, root, detected in candidates
    ]


def _read_bundle(resource_root: Path) -> dict[str, str]:
    return {
        relative_path: resource_root.joinpath(*relative_path.split("/")).read_text(
            encoding="utf-8"
        )
        for relative_path in BUNDLED_FILES
    }


def _install_skill(target: Path, contents: Mapping[str, str]) -> bool:
    bundled_hash = _content_hash(contents)
    current_hash = _installed_hash(target)
    managed_hash = _managed_hash(target)

    if current_hash == bundled_hash:
        if managed_hash != bundled_hash:
            target.mkdir(parents=True, exist_ok=True)
            _write_marker(target, bundled_hash)
        return False

    if (
        target.exists()
        and any(target.iterdir())
        and (managed_hash is None or current_hash != managed_hash)
    ):
        return False

    for relative_path, content in contents.items():
        destination = target.joinpath(*relative_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(destination, content)
    _write_marker(target, bundled_hash)
    return True


def _installed_hash(target: Path) -> str | None:
    try:
        contents = {
            relative_path: target.joinpath(*relative_path.split("/")).read_text(encoding="utf-8")
            for relative_path in BUNDLED_FILES
        }
    except OSError:
        return None
    return _content_hash(contents)


def _managed_hash(target: Path) -> str | None:
    try:
        marker = json.loads((target / MANAGED_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    content_hash = marker.get("content_sha256") if isinstance(marker, dict) else None
    return content_hash if isinstance(content_hash, str) else None


def _content_hash(contents: Mapping[str, str]) -> str:
    digest = sha256()
    for relative_path in sorted(contents):
        digest.update(relative_path.encode())
        digest.update(b"\0")
        digest.update(contents[relative_path].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_marker(target: Path, content_hash: str) -> None:
    marker = json.dumps(
        {"content_sha256": content_hash, "package_version": __version__},
        sort_keys=True,
    )
    _atomic_write(target / MANAGED_FILE, f"{marker}\n")


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
