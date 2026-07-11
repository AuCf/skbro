from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import SkmError
from .models import SkillManifest
from .storage import (
    load_config,
    load_registry,
    save_registry,
    skill_source_path,
    skills_dir,
)


@dataclass(slots=True)
class DoctorIssue:
    level: str
    code: str
    message: str
    repaired: bool = False


def _link_path(record: dict[str, object]) -> Path:
    project_value = record.get("project")
    relative_value = record.get("relative_path")
    if not isinstance(project_value, str) or not project_value:
        raise SkmError("Link record has no project path.")
    if not isinstance(relative_value, str) or not relative_value:
        raise SkmError("Link record has no relative target path.")
    project = Path(project_value).resolve()
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise SkmError("Link record target points outside its project.")
    parent = (project / relative).parent.resolve()
    try:
        parent.relative_to(project)
    except ValueError as exc:
        raise SkmError("Link record target points outside its project.") from exc
    return project / relative


def run_doctor(*, repair: bool = False) -> list[DoctorIssue]:
    issues: list[DoctorIssue] = []
    try:
        load_config()
    except SkmError as exc:
        issues.append(DoctorIssue("error", "config", str(exc)))

    try:
        registry = load_registry()
    except SkmError as exc:
        issues.append(DoctorIssue("error", "registry", str(exc)))
        return issues

    changed = False
    registered_paths: set[Path] = set()
    for name, skill in sorted(registry["skills"].items()):
        try:
            source = skill_source_path(skill)
            registered_paths.add(source.resolve())
        except SkmError as exc:
            issues.append(DoctorIssue("error", "unsafe-skill-path", f"{name}: {exc}"))
            continue

        if not source.exists():
            issues.append(
                DoctorIssue("error", "missing-skill", f"{name}: source is missing: {source}")
            )
        elif source.is_dir():
            try:
                manifest = SkillManifest.load(source)
                if manifest.name != name:
                    issues.append(
                        DoctorIssue(
                            "error",
                            "name-mismatch",
                            f"{name}: manifest name is {manifest.name}",
                        )
                    )
            except SkmError as exc:
                issues.append(DoctorIssue("error", "manifest", f"{name}: {exc}"))
        elif not source.is_file():
            issues.append(
                DoctorIssue("error", "invalid-skill-source", f"{name}: invalid source: {source}")
            )

        links = skill.get("links", [])
        if not isinstance(links, list):
            issues.append(DoctorIssue("error", "links", f"{name}: links must be a list"))
            continue
        for record in list(links):
            if not isinstance(record, dict):
                issues.append(DoctorIssue("error", "link-record", f"{name}: invalid link record"))
                continue
            try:
                target = _link_path(record)
            except SkmError as exc:
                issues.append(DoctorIssue("error", "unsafe-link", f"{name}: {exc}"))
                continue
            if target.exists():
                continue
            state = "broken link" if target.is_symlink() else "missing target"
            item = DoctorIssue(
                "warning",
                "missing-link",
                f"{name}: {state}: {target}",
            )
            if repair:
                if target.is_symlink():
                    target.unlink(missing_ok=True)
                links.remove(record)
                item.repaired = True
                changed = True
            issues.append(item)

    if skills_dir().is_dir():
        for path in sorted(skills_dir().iterdir()):
            if path.resolve() not in registered_paths:
                issues.append(
                    DoctorIssue(
                        "warning",
                        "orphan-storage",
                        f"Unregistered item in skill storage: {path}",
                    )
                )

    if changed:
        save_registry(registry)
    return issues
