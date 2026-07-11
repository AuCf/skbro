from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import SkmError
from .models import validate_skill_name


APP_DIR_NAME = ".skill_manager"
CONFIG_FILE = "config.json"
REGISTRY_FILE = "registry.json"
SKILLS_DIR = "skills"
LEGACY_REGISTRY_DIR = "registry"
REGISTRY_SCHEMA_VERSION = 2

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "default_target": "default",
    "link_mode": "symlink",
    "targets": {
        "default": ".skills",
        "codex": ".codex/skills",
        "claude": ".claude/skills",
    },
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def skm_home() -> Path:
    override = os.environ.get("SKM_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / APP_DIR_NAME


def config_path() -> Path:
    return skm_home() / CONFIG_FILE


def registry_path() -> Path:
    return skm_home() / REGISTRY_FILE


def skills_dir() -> Path:
    return skm_home() / SKILLS_DIR


def skill_dir(name: str) -> Path:
    validate_skill_name(name)
    return skills_dir() / name


def empty_registry() -> dict[str, Any]:
    return {"schema_version": REGISTRY_SCHEMA_VERSION, "skills": {}}


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        json.loads(temp_path.read_text(encoding="utf-8"))
        os.replace(temp_path, path)
    except (OSError, json.JSONDecodeError) as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise SkmError(f"Failed to write JSON file: {path}\nReason: {exc}") from exc


def init_storage() -> tuple[bool, bool, bool]:
    home = skm_home()
    if home.exists() and not home.is_dir():
        raise SkmError(f"Skill Manager home is not a directory: {home}")
    created_home = not home.exists()
    home.mkdir(parents=True, exist_ok=True)

    created_config = not config_path().exists()
    if created_config:
        write_json_atomic(config_path(), DEFAULT_CONFIG)

    created_registry = not registry_path().exists()
    if created_registry:
        write_json_atomic(registry_path(), empty_registry())

    skills_dir().mkdir(parents=True, exist_ok=True)
    (home / LEGACY_REGISTRY_DIR).mkdir(parents=True, exist_ok=True)
    return created_home, created_config, created_registry


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkmError(f"{label} file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SkmError(f"Invalid {label} JSON: {path}") from exc
    except OSError as exc:
        raise SkmError(f"Failed to read {label}: {path}\nReason: {exc}") from exc
    if not isinstance(data, dict):
        raise SkmError(f"Invalid {label} structure. Expected a JSON object: {path}")
    return data


def _validate_target_dir(value: Any, target: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkmError(f"Invalid target directory for '{target}'.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise SkmError(
            f"Invalid target directory for '{target}'. Use a path inside the project."
        )
    return value


def _normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version", 1) != 1:
        raise SkmError(f"Unsupported config schema: {data.get('schema_version')}")

    # Migrate the original MVP shape in memory.
    targets = dict(DEFAULT_CONFIG["targets"])
    configured_targets = data.get("targets", {})
    if not isinstance(configured_targets, dict):
        raise SkmError("Invalid config targets. Expected a JSON object.")
    targets.update(configured_targets)
    legacy_target = data.get("project_skill_dir")
    if legacy_target is not None:
        targets["default"] = legacy_target

    for name, value in targets.items():
        if not isinstance(name, str) or not name:
            raise SkmError("Invalid config target name.")
        targets[name] = _validate_target_dir(value, name)

    link_mode = data.get("link_mode", DEFAULT_CONFIG["link_mode"])
    if link_mode not in {"symlink", "copy"}:
        raise SkmError("Invalid config link_mode. Expected: symlink or copy")
    default_target = data.get("default_target", DEFAULT_CONFIG["default_target"])
    if not isinstance(default_target, str) or default_target not in targets:
        raise SkmError("Invalid config default_target. Expected a configured target name.")

    return {
        "schema_version": 1,
        "default_target": default_target,
        "link_mode": link_mode,
        "targets": targets,
    }


def load_config() -> dict[str, Any]:
    init_storage()
    return _normalize_config(_read_json_object(config_path(), "config"))


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_config(config)
    write_json_atomic(config_path(), normalized)
    return normalized


def load_registry() -> dict[str, Any]:
    init_storage()
    registry = _read_json_object(registry_path(), "registry")
    schema_version = registry.get("schema_version", 1)
    if schema_version not in {1, REGISTRY_SCHEMA_VERSION}:
        raise SkmError(f"Unsupported registry schema: {schema_version}")
    skills = registry.get("skills")
    if not isinstance(skills, dict):
        raise SkmError(f"Invalid registry skills structure: {registry_path()}")
    for name, skill in skills.items():
        if not isinstance(name, str) or not isinstance(skill, dict):
            raise SkmError(f"Invalid skill entry in registry: {name}")
    registry["schema_version"] = REGISTRY_SCHEMA_VERSION
    return registry


def save_registry(registry: dict[str, Any]) -> None:
    registry["schema_version"] = REGISTRY_SCHEMA_VERSION
    write_json_atomic(registry_path(), registry)


def require_skill(registry: dict[str, Any], name: str) -> dict[str, Any]:
    validate_skill_name(name)
    skill = registry["skills"].get(name)
    if skill is None:
        raise SkmError(f"Skill not found: {name}")
    if not isinstance(skill, dict):
        raise SkmError(f"Invalid skill entry: {name}")
    return skill


def safe_home_path(relative: str, label: str = "path") -> Path:
    if not isinstance(relative, str) or not relative:
        raise SkmError(f"Invalid {label} in registry.")
    candidate = (skm_home() / relative).resolve()
    try:
        candidate.relative_to(skm_home().resolve())
    except ValueError as exc:
        raise SkmError(f"Invalid {label}; it points outside Skill Manager home.") from exc
    return candidate


def skill_source_path(skill: dict[str, Any]) -> Path:
    if isinstance(skill.get("path"), str):
        return safe_home_path(skill["path"], "skill path")
    if isinstance(skill.get("file"), str):
        return safe_home_path(skill["file"], "legacy skill file")
    raise SkmError(f"Invalid skill path for: {skill.get('name', '<unknown>')}")


def project_target_path(project: Path, target_dir: str, leaf_name: str) -> Path:
    if Path(leaf_name).name != leaf_name or leaf_name in {"", ".", ".."}:
        raise SkmError("Invalid project target name.")
    project = project.resolve()
    target_root = (project / target_dir).resolve()
    try:
        target_root.relative_to(project)
    except ValueError as exc:
        raise SkmError("Target path points outside the current project.") from exc
    return target_root / leaf_name
