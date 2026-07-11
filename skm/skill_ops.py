from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .errors import SkmError
from .models import DEFAULT_ENTRY, MANIFEST_FILE, SkillManifest, parse_tags
from .storage import (
    load_registry,
    now_iso,
    require_skill,
    save_registry,
    skill_dir,
    skill_source_path,
    skm_home,
    write_json_atomic,
)


def _check_portable_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SkmError(
                f"Skill packages cannot contain symbolic links: {path.relative_to(root)}"
            )


def _apply_overrides(
    manifest: SkillManifest,
    *,
    name: str | None = None,
    version: str | None = None,
    description: str | None = None,
    note: str | None = None,
    tags: str | list[str] | None = None,
) -> SkillManifest:
    if name is not None:
        manifest.name = name
    if version is not None:
        manifest.version = version
    if description is not None:
        manifest.description = description
    if note is not None:
        manifest.note = note
    if tags is not None:
        manifest.tags = parse_tags(tags)
    manifest.validate()
    return manifest


def create_skill(
    name: str,
    destination: Path,
    *,
    version: str = "0.1.0",
    description: str = "",
    note: str = "",
    tags: str | list[str] | None = None,
    author: str = "",
    license_name: str = "",
) -> Path:
    manifest = SkillManifest(
        name=name,
        version=version,
        description=description,
        note=note,
        tags=parse_tags(tags),
        author=author,
        license=license_name,
    )
    manifest.validate()
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise SkmError(f"Destination already exists: {destination}")
    try:
        destination.mkdir(parents=True)
        write_json_atomic(destination / MANIFEST_FILE, manifest.to_dict())
        title = description or name
        (destination / DEFAULT_ENTRY).write_text(
            f"# {title}\n\nDescribe when and how this skill should be used.\n",
            encoding="utf-8",
        )
    except (OSError, SkmError) as exc:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        if isinstance(exc, SkmError):
            raise
        raise SkmError(f"Failed to create skill: {destination}\nReason: {exc}") from exc
    return destination


def _prepare_local_source(
    source: Path,
    payload: Path,
    *,
    name: str | None,
    version: str | None,
    description: str | None,
    note: str | None,
    tags: str | list[str] | None,
) -> SkillManifest:
    source = source.expanduser().resolve()
    if not source.exists():
        raise SkmError(f"Source not found: {source}")

    if source.is_file():
        if source.suffix.lower() != ".md":
            raise SkmError("Only Markdown files or skill directories can be added.")
        payload.mkdir()
        shutil.copy2(source, payload / DEFAULT_ENTRY)
        manifest = SkillManifest(name=name or source.stem)
    elif source.is_dir():
        _check_portable_tree(source)
        shutil.copytree(source, payload)
        manifest_path = payload / MANIFEST_FILE
        if manifest_path.is_file():
            manifest = SkillManifest.load(payload)
        else:
            entry = payload / DEFAULT_ENTRY
            if not entry.is_file():
                raise SkmError(
                    f"Skill directory must contain {DEFAULT_ENTRY}: {source}"
                )
            manifest = SkillManifest(name=name or source.name)
    else:
        raise SkmError(f"Unsupported source: {source}")

    manifest = _apply_overrides(
        manifest,
        name=name,
        version=version,
        description=description,
        note=note,
        tags=tags,
    )
    manifest.validate(payload)
    write_json_atomic(payload / MANIFEST_FILE, manifest.to_dict())
    return manifest


def add_local_skill(
    source: Path,
    *,
    name: str | None = None,
    version: str | None = None,
    description: str | None = None,
    note: str | None = None,
    tags: str | list[str] | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = source.expanduser().resolve()
    registry = load_registry()
    skm_home().mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".install-", dir=skm_home()) as temp:
        payload = Path(temp) / "payload"
        try:
            manifest = _prepare_local_source(
                source,
                payload,
                name=name,
                version=version,
                description=description,
                note=note,
                tags=tags,
            )
        except OSError as exc:
            raise SkmError(f"Failed to read skill source: {source}\nReason: {exc}") from exc

        if manifest.name in registry["skills"]:
            raise SkmError(f"Skill already exists: {manifest.name}")
        destination = skill_dir(manifest.name)
        if destination.exists():
            raise SkmError(
                f"Skill storage already exists without a registry entry: {destination}\n"
                "Run 'skbro doctor' before trying again."
            )

        timestamp = now_iso()
        metadata = source_metadata or {
            "type": "local",
            "location": str(source),
        }
        record = {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "note": manifest.note,
            "tags": manifest.tags,
            "path": f"skills/{manifest.name}",
            "entry": manifest.entry,
            "source": metadata,
            "links": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        }

        try:
            os.replace(payload, destination)
            registry["skills"][manifest.name] = record
            save_registry(registry)
        except (OSError, SkmError) as exc:
            registry["skills"].pop(manifest.name, None)
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            if isinstance(exc, SkmError):
                raise
            raise SkmError(
                f"Failed to install skill: {manifest.name}\nReason: {exc}"
            ) from exc
    return record


def update_local_skill(
    name: str,
    source: Path,
    *,
    source_metadata: dict[str, Any],
) -> dict[str, Any]:
    registry = load_registry()
    previous = require_skill(registry, name)
    current_source = skill_source_path(previous)

    with tempfile.TemporaryDirectory(prefix=".update-", dir=skm_home()) as temp:
        payload = Path(temp) / "payload"
        manifest = _prepare_local_source(
            source,
            payload,
            name=name if source.is_file() else None,
            version=None,
            description=None,
            note=None,
            tags=None,
        )
        if manifest.name != name:
            raise SkmError(
                f"Updated skill name does not match: expected {name}, got {manifest.name}"
            )

        timestamp = now_iso()
        replacement = {
            **previous,
            "name": name,
            "version": manifest.version,
            "description": manifest.description,
            "note": manifest.note,
            "tags": manifest.tags,
            "path": f"skills/{name}",
            "entry": manifest.entry,
            "source": source_metadata,
            "updated_at": timestamp,
        }
        replacement.pop("file", None)
        destination = skill_dir(name)
        backup = Path(temp) / "backup"
        try:
            if current_source.exists() or current_source.is_symlink():
                os.replace(current_source, backup)
            os.replace(payload, destination)
            registry["skills"][name] = replacement
            save_registry(registry)
        except (OSError, SkmError) as exc:
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            if backup.exists():
                os.replace(backup, current_source)
            registry["skills"][name] = previous
            if isinstance(exc, SkmError):
                raise
            raise SkmError(f"Failed to update skill: {name}\nReason: {exc}") from exc
    return replacement


def remove_skill(name: str) -> Path:
    registry = load_registry()
    skill = registry["skills"].get(name)
    if not isinstance(skill, dict):
        raise SkmError(f"Skill not found: {name}")
    links = skill.get("links", [])
    legacy_links = skill.get("linked_projects", [])
    if links or legacy_links:
        raise SkmError(
            f"Skill is still used by one or more projects: {name}\n"
            "Run 'skbro unuse' in those projects first."
        )
    source = skill_source_path(skill)
    del registry["skills"][name]
    save_registry(registry)
    try:
        if source.is_dir():
            shutil.rmtree(source)
        elif source.exists() or source.is_symlink():
            source.unlink()
    except OSError as exc:
        registry["skills"][name] = skill
        save_registry(registry)
        raise SkmError(f"Failed to remove skill files: {source}\nReason: {exc}") from exc
    return source


def load_installed_manifest(skill: dict[str, Any]) -> SkillManifest:
    source = skill_source_path(skill)
    if source.is_dir():
        return SkillManifest.load(source)
    if source.is_file():
        return SkillManifest(
            name=str(skill.get("name", source.stem)),
            version=str(skill.get("version", "0.1.0")),
            description=str(skill.get("description", "")),
            note=str(skill.get("note", "")),
            tags=parse_tags(skill.get("tags", [])),
        )
    raise SkmError(f"Skill source not found: {source}")
