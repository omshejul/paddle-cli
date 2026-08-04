from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from paddle_cli import __version__

SKILL_NAME = "paddle-cli"
MANAGED_FILE = ".paddle-cli-managed.json"
BUNDLED_FILES = ("SKILL.md", "agents/openai.yaml")
SHARED_AGENTS = "Codex, Cursor, Gemini CLI, GitHub Copilot, and OpenCode"


@dataclass(frozen=True)
class SkillInstallation:
    agent: str
    path: Path


def ensure_agent_skills(
    *,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    resource_root: Path | None = None,
) -> list[SkillInstallation]:
    """Install one shared skill, with a Claude Code link when Claude is present."""
    resolved_home = home or Path.home()
    resolved_environ = environ if environ is not None else os.environ
    resolved_resources = resource_root or Path(__file__).with_name("bundled_skill")
    try:
        contents = _read_bundle(resolved_resources)
    except OSError:
        return []

    installed: list[SkillInstallation] = []
    shared = resolved_home / ".agents" / "skills" / SKILL_NAME
    try:
        if _install_skill(shared, contents):
            installed.append(SkillInstallation(SHARED_AGENTS, shared))
    except (OSError, ValueError):
        return []

    claude_root = resolved_home / ".claude"
    if claude_root.exists():
        claude_skill = claude_root / "skills" / SKILL_NAME
        try:
            if _ensure_claude_skill(claude_skill, shared, contents):
                installed.append(SkillInstallation("Claude Code", claude_skill))
        except (OSError, ValueError):
            pass

    for legacy in _legacy_skill_paths(resolved_home, resolved_environ):
        if legacy == shared:
            continue
        try:
            _remove_pristine_managed_skill(legacy)
        except OSError:
            continue
    return installed


def _legacy_skill_paths(home: Path, environ: Mapping[str, str]) -> tuple[Path, ...]:
    codex_home = Path(environ.get("CODEX_HOME", home / ".codex")).expanduser()
    roots = (
        codex_home,
        home / ".cursor",
        home / ".gemini",
        home / ".copilot",
        home / ".config" / "opencode",
        home / ".config" / "agents",
    )
    return tuple(root / "skills" / SKILL_NAME for root in roots)


def _ensure_claude_skill(
    target: Path,
    shared: Path,
    contents: Mapping[str, str],
) -> bool:
    if target.is_symlink():
        return False
    if target.exists() and not _remove_pristine_managed_skill(target):
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(shared, target_is_directory=True)
    except OSError:
        return _install_skill(target, contents)
    return True


def _remove_pristine_managed_skill(target: Path) -> bool:
    if target.is_symlink() or not target.is_dir():
        return False
    managed_hash = _managed_hash(target)
    if managed_hash is None or _installed_hash(target) != managed_hash:
        return False
    files = {
        item.relative_to(target).as_posix()
        for item in target.rglob("*")
        if item.is_file()
    }
    if files != {*BUNDLED_FILES, MANAGED_FILE}:
        return False
    shutil.rmtree(target)
    return True


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
