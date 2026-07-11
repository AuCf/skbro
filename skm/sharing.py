from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from .errors import SkmError
from .models import DEFAULT_ENTRY, MANIFEST_FILE, SkillManifest, parse_tags
from .storage import load_registry, require_skill, skill_source_path


IGNORED_PARTS = {".git", "__pycache__", ".DS_Store"}


def _manifest_for_legacy(skill: dict[str, Any]) -> SkillManifest:
    return SkillManifest(
        name=str(skill.get("name", "")),
        version=str(skill.get("version", "0.1.0")),
        description=str(skill.get("description", "")),
        note=str(skill.get("note", "")),
        tags=parse_tags(skill.get("tags", [])),
    )


def pack_skill(name: str, output: Path | None = None, *, force: bool = False) -> Path:
    registry = load_registry()
    skill = require_skill(registry, name)
    source = skill_source_path(skill)
    if not source.exists():
        raise SkmError(f"Skill source not found: {source}")
    version = str(skill.get("version", "0.1.0"))
    output = (output or Path.cwd() / f"{name}-{version}.zip").expanduser().resolve()
    if source.is_dir():
        try:
            output.relative_to(source.resolve())
        except ValueError:
            pass
        else:
            raise SkmError("Package output must be outside the installed skill directory.")
    if output.exists() and not force:
        raise SkmError(f"Output already exists: {output}\nUse --force to replace it.")
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            if source.is_file():
                bundle.write(source, DEFAULT_ENTRY)
                manifest = _manifest_for_legacy(skill)
                bundle.writestr(
                    MANIFEST_FILE,
                    json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
                )
            else:
                for path in sorted(source.rglob("*")):
                    relative = path.relative_to(source)
                    if any(part in IGNORED_PARTS for part in relative.parts):
                        continue
                    if path.is_symlink():
                        raise SkmError(f"Cannot pack symbolic link: {relative}")
                    if path.is_file():
                        bundle.write(path, relative.as_posix())
    except SkmError:
        output.unlink(missing_ok=True)
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        output.unlink(missing_ok=True)
        raise SkmError(f"Failed to pack skill: {name}\nReason: {exc}") from exc
    return output
