from __future__ import annotations

import os
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .errors import SkmError
from .storage import (
    load_config,
    load_registry,
    now_iso,
    project_target_path,
    require_skill,
    save_registry,
    skill_source_path,
)


def current_project() -> Path:
    return Path.cwd().resolve()


def project_key(project: Path) -> str:
    return os.path.normcase(str(project.resolve()))


def _links(skill: dict[str, Any]) -> list[dict[str, Any]]:
    links = skill.setdefault("links", [])
    if not isinstance(links, list) or any(not isinstance(item, dict) for item in links):
        raise SkmError(f"Invalid link records for: {skill.get('name', '<unknown>')}")
    return links


def _leaf_name(skill: dict[str, Any], source: Path) -> str:
    name = str(skill.get("name", ""))
    return name if source.is_dir() else f"{name}.md"


def create_project_link(source: Path, target: Path, mode: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if mode == "copy":
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
            return
        target.symlink_to(source, target_is_directory=source.is_dir())
    except OSError as exc:
        raise SkmError(
            "Failed to place skill in the project.\n\n"
            f"Reason: {exc}\n\n"
            "Try again with --copy if symbolic links are unavailable."
        ) from exc


def use_skill(
    name: str,
    *,
    target_name: str | None = None,
    copy: bool = False,
    project: Path | None = None,
) -> dict[str, Any]:
    project = (project or current_project()).resolve()
    config = load_config()
    registry = load_registry()
    skill = require_skill(registry, name)
    source = skill_source_path(skill)
    if not source.exists():
        raise SkmError(f"Skill source not found: {source}")

    target_name = target_name or config["default_target"]
    target_dir = config["targets"].get(target_name)
    if target_dir is None:
        available = ", ".join(sorted(config["targets"]))
        raise SkmError(f"Unknown target: {target_name}\nAvailable targets: {available}")
    mode = "copy" if copy else config["link_mode"]
    leaf = _leaf_name(skill, source)
    target = project_target_path(project, target_dir, leaf)
    if target.exists() or target.is_symlink():
        raise SkmError(f"Project target already exists: {target}")

    links = _links(skill)
    key = project_key(project)
    if any(
        project_key(Path(str(item.get("project", "")))) == key
        and item.get("target") == target_name
        for item in links
        if item.get("project")
    ):
        raise SkmError(f"Skill is already used in this project target: {name}")

    create_project_link(source, target, mode)
    relative_path = str(target.relative_to(project))
    record = {
        "project": str(project),
        "target": target_name,
        "relative_path": relative_path,
        "mode": mode,
        "created_at": now_iso(),
    }
    if mode == "copy":
        record["digest"] = _content_digest(source)
    links.append(record)
    skill["updated_at"] = now_iso()
    try:
        save_registry(registry)
    except SkmError:
        _remove_target(target, mode)
        links.remove(record)
        raise
    return record


def _record_target(project: Path, record: dict[str, Any]) -> Path:
    relative = record.get("relative_path")
    if not isinstance(relative, str) or not relative:
        raise SkmError("Invalid project link path in registry.")
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise SkmError("Project link path points outside the project.")
    target = project / relative_path
    parent = target.parent.resolve()
    try:
        parent.relative_to(project.resolve())
    except ValueError as exc:
        raise SkmError("Project link path points outside the project.") from exc
    return target


def _remove_target(target: Path, mode: str) -> None:
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        if mode != "copy":
            raise SkmError(f"Refusing to remove an unexpected directory: {target}")
        shutil.rmtree(target)


def _content_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            digest.update(f"link:{item.relative_to(path)}".encode())
            digest.update(str(item.resolve()).encode())
        elif item.is_file():
            digest.update(item.relative_to(path).as_posix().encode())
            digest.update(b"\0")
            with item.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
    return digest.hexdigest()


def unuse_skill(
    name: str,
    *,
    target_name: str | None = None,
    force: bool = False,
    project: Path | None = None,
) -> list[dict[str, Any]]:
    project = (project or current_project()).resolve()
    registry = load_registry()
    skill = require_skill(registry, name)
    key = project_key(project)
    links = _links(skill)
    matches = [
        item
        for item in links
        if item.get("project")
        and project_key(Path(str(item["project"]))) == key
        and (target_name is None or item.get("target") == target_name)
    ]

    # Compatibility with the original registry format.
    legacy_projects = skill.get("linked_projects", [])
    if not matches and isinstance(legacy_projects, list) and str(project) in legacy_projects:
        legacy_target = project / ".skills" / f"{name}.md"
        if legacy_target.exists() or legacy_target.is_symlink():
            if legacy_target.is_dir() and not legacy_target.is_symlink():
                raise SkmError(f"Refusing to remove a directory: {legacy_target}")
            legacy_target.unlink()
        skill["linked_projects"] = [item for item in legacy_projects if item != str(project)]
        skill["updated_at"] = now_iso()
        save_registry(registry)
        return [{"project": str(project), "target": "legacy", "relative_path": str(legacy_target.relative_to(project)), "mode": "symlink"}]

    if not matches:
        raise SkmError(f"Skill is not used in the current project: {name}")

    removed: list[tuple[Path, dict[str, Any]]] = []
    try:
        for record in matches:
            target = _record_target(project, record)
            if target.exists() or target.is_symlink():
                expected_digest = record.get("digest")
                if (
                    record.get("mode") == "copy"
                    and isinstance(expected_digest, str)
                    and _content_digest(target) != expected_digest
                    and not force
                ):
                    raise SkmError(
                        f"Project copy was modified: {target}\n"
                        "Use --force to remove it anyway."
                    )
                _remove_target(target, str(record.get("mode", "symlink")))
            links.remove(record)
            removed.append((target, record))
        skill["updated_at"] = now_iso()
        save_registry(registry)
    except (OSError, SkmError) as exc:
        if isinstance(exc, SkmError):
            raise
        raise SkmError(f"Failed to remove project skill: {exc}") from exc
    return [record for _, record in removed]


def project_status(project: Path | None = None) -> list[dict[str, Any]]:
    project = (project or current_project()).resolve()
    registry = load_registry()
    key = project_key(project)
    result: list[dict[str, Any]] = []
    for name, skill in sorted(registry["skills"].items()):
        if not isinstance(skill, dict):
            continue
        for record in _links(skill):
            raw_project = record.get("project")
            if not raw_project or project_key(Path(str(raw_project))) != key:
                continue
            target = _record_target(project, record)
            source = skill_source_path(skill)
            state = "ok" if target.exists() else "missing"
            if target.is_symlink() and not target.exists():
                state = "broken"
            elif target.exists() and record.get("mode") == "copy":
                target_digest = _content_digest(target)
                source_digest = _content_digest(source)
                recorded_digest = record.get("digest")
                if target_digest == source_digest:
                    state = "ok"
                elif isinstance(recorded_digest, str) and target_digest != recorded_digest:
                    state = "modified"
                else:
                    state = "outdated"
            elif target.is_symlink() and target.resolve() != source.resolve():
                state = "wrong"
            result.append(
                {
                    "name": name,
                    "target": record.get("target", "default"),
                    "mode": record.get("mode", "symlink"),
                    "path": str(target.relative_to(project)),
                    "state": state,
                }
            )
    return result


def sync_project_skills(
    name: str | None = None,
    *,
    project: Path | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    project = (project or current_project()).resolve()
    registry = load_registry()
    key = project_key(project)
    synced: list[dict[str, Any]] = []
    for skill_name, skill in sorted(registry["skills"].items()):
        if name is not None and skill_name != name:
            continue
        if not isinstance(skill, dict):
            continue
        source = skill_source_path(skill)
        if not source.exists():
            raise SkmError(f"Skill source not found: {source}")
        for record in _links(skill):
            raw_project = record.get("project")
            if (
                not raw_project
                or project_key(Path(str(raw_project))) != key
                or record.get("mode") != "copy"
            ):
                continue
            target = _record_target(project, record)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and isinstance(record.get("digest"), str):
                if _content_digest(target) != record["digest"] and not force:
                    raise SkmError(
                        f"Project copy was modified: {target}\n"
                        "Use --force to replace local changes."
                    )
            with tempfile.TemporaryDirectory(prefix=".skbro-sync-", dir=target.parent) as temp:
                staged = Path(temp) / target.name
                backup = Path(temp) / "backup"
                try:
                    if source.is_dir():
                        shutil.copytree(source, staged)
                    else:
                        shutil.copy2(source, staged)
                    if target.exists() or target.is_symlink():
                        os.replace(target, backup)
                    os.replace(staged, target)
                except OSError as exc:
                    if backup.exists() or backup.is_symlink():
                        if target.exists() or target.is_symlink():
                            _remove_target(target, "copy")
                        os.replace(backup, target)
                    raise SkmError(
                        f"Failed to sync {skill_name} to {target}\nReason: {exc}"
                    ) from exc
            record["digest"] = _content_digest(source)
            synced.append(
                {
                    "name": skill_name,
                    "target": record.get("target", "default"),
                    "path": str(target.relative_to(project)),
                }
            )
    if synced:
        save_registry(registry)
    if name is not None and not synced:
        skill = registry["skills"].get(name)
        if skill is None:
            raise SkmError(f"Skill not found: {name}")
        raise SkmError(f"No copy-mode project usage found for: {name}")
    return synced
