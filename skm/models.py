from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import SkmError


VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MANIFEST_FILE = "skill.json"
DEFAULT_ENTRY = "SKILL.md"


def validate_skill_name(name: str) -> str:
    if not isinstance(name, str) or not VALID_NAME.fullmatch(name):
        raise SkmError(
            f"Invalid skill name: {name}\n"
            "Use letters, numbers, dots, underscores, and hyphens."
        )
    return name


def parse_tags(raw_tags: str | list[str] | None) -> list[str]:
    if raw_tags is None:
        return []
    values = raw_tags if isinstance(raw_tags, list) else raw_tags.split(",")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value).strip()
        key = tag.casefold()
        if tag and key not in seen:
            result.append(tag)
            seen.add(key)
    return result


@dataclass(slots=True)
class SkillManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    note: str = ""
    tags: list[str] = field(default_factory=list)
    author: str = ""
    license: str = ""
    entry: str = DEFAULT_ENTRY
    schema_version: int = 1

    def validate(self, root: Path | None = None) -> None:
        validate_skill_name(self.name)
        if not isinstance(self.version, str) or not self.version.strip():
            raise SkmError("Invalid skill version. Expected a non-empty string.")
        if not isinstance(self.entry, str) or not self.entry.strip():
            raise SkmError("Invalid skill entry. Expected a non-empty relative path.")
        entry_path = Path(self.entry)
        if entry_path.is_absolute() or ".." in entry_path.parts:
            raise SkmError("Invalid skill entry. It must stay inside the skill directory.")
        if root is not None:
            full_entry = (root / entry_path).resolve()
            try:
                full_entry.relative_to(root.resolve())
            except ValueError as exc:
                raise SkmError("Skill entry points outside the skill directory.") from exc
            if not full_entry.is_file():
                raise SkmError(f"Skill entry not found: {self.entry}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "note": self.note,
            "tags": self.tags,
            "author": self.author,
            "license": self.license,
            "entry": self.entry,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillManifest":
        if not isinstance(data, dict):
            raise SkmError("Invalid skill manifest. Expected a JSON object.")
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            raise SkmError("Invalid skill manifest tags. Expected a list.")
        manifest = cls(
            schema_version=data.get("schema_version", 1),
            name=data.get("name", ""),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            note=data.get("note", ""),
            tags=parse_tags(tags),
            author=data.get("author", ""),
            license=data.get("license", ""),
            entry=data.get("entry", DEFAULT_ENTRY),
        )
        for field_name in ("description", "note", "author", "license"):
            if not isinstance(getattr(manifest, field_name), str):
                raise SkmError(f"Invalid skill manifest field: {field_name}")
        if manifest.schema_version != 1:
            raise SkmError(
                f"Unsupported skill manifest schema: {manifest.schema_version}"
            )
        manifest.validate()
        return manifest

    @classmethod
    def load(cls, root: Path) -> "SkillManifest":
        path = root / MANIFEST_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SkmError(f"Skill manifest not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise SkmError(f"Invalid skill manifest JSON: {path}") from exc
        manifest = cls.from_dict(data)
        manifest.validate(root)
        return manifest
