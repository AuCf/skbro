from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .errors import SkmError
from .doctor import run_doctor
from .project_ops import (
    current_project,
    project_status,
    sync_project_skills,
    unuse_skill,
    use_skill,
)
from .sharing import pack_skill
from .skill_ops import add_local_skill, create_skill, remove_skill, update_local_skill
from .sources import prepare_source
from .storage import (
    config_path,
    init_storage,
    load_config,
    load_registry,
    registry_path,
    require_skill,
    save_config,
    skill_source_path,
    skills_dir,
    skm_home,
)


VERSION = __version__


def truncate(text: str, limit: int = 36) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "..."


def _project_is_linked(skill: dict[str, Any], project: Path) -> bool:
    key = os.path.normcase(str(project.resolve()))
    links = skill.get("links", [])
    if isinstance(links, list):
        for item in links:
            if not isinstance(item, dict) or not item.get("project"):
                continue
            item_key = os.path.normcase(str(Path(str(item["project"])).resolve()))
            if item_key == key:
                return True
    legacy = skill.get("linked_projects", [])
    return isinstance(legacy, list) and any(
        os.path.normcase(str(Path(str(item)).resolve())) == key for item in legacy
    )


def command_init(_args: argparse.Namespace) -> int:
    created_home, created_config, created_registry = init_storage()
    status = (
        "initialized"
        if any((created_home, created_config, created_registry))
        else "already initialized"
    )
    print(f"Skill Manager {status}.")
    print()
    print(f"Home: {skm_home()}")
    print(f"Config: {config_path()}")
    print(f"Registry: {registry_path()}")
    print(f"Skills: {skills_dir()}")
    return 0


def command_create(args: argparse.Namespace) -> int:
    destination = Path(args.path) if args.path else Path.cwd() / args.name
    created = create_skill(
        args.name,
        destination,
        version=args.version,
        description=args.description or "",
        note=args.note or "",
        tags=args.tags,
        author=args.author or "",
        license_name=args.license or "",
    )
    print("Skill created.")
    print()
    print(f"Path: {created}")
    print(f"Entry: {created / 'SKILL.md'}")
    print()
    print(f"Next: skm add {created}")
    return 0


def _print_added(record: dict[str, Any]) -> None:
    print("Skill added.")
    print()
    print(f"Name: {record['name']}")
    print(f"Version: {record.get('version', '')}")
    print(f"Path: {skill_source_path(record)}")


def command_add(args: argparse.Namespace) -> int:
    with prepare_source(args.source, force_git=args.git, ref=args.ref) as (source, metadata):
        suggested_name = metadata.pop("suggested_name", None)
        effective_name = args.name
        if effective_name is None and not (source.is_dir() and (source / "skill.json").is_file()):
            effective_name = suggested_name
        record = add_local_skill(
            source,
            name=effective_name,
            version=args.version,
            description=args.description,
            note=args.note,
            tags=args.tags,
            source_metadata=metadata,
        )
    _print_added(record)
    return 0


def command_register(args: argparse.Namespace) -> int:
    record = add_local_skill(
        Path(args.file),
        name=args.name,
        description=args.description,
        note=args.note,
        tags=args.tags,
    )
    _print_added(record)
    return 0


def command_list(_args: argparse.Namespace) -> int:
    registry = load_registry()
    skills = registry["skills"]
    if not skills:
        print("No skills installed.")
        return 0

    project = current_project()
    print(f"{'NAME':<24}{'VERSION':<12}{'USED':<8}{'TAGS':<26}DESCRIPTION")
    for name in sorted(skills):
        skill = skills[name]
        if not isinstance(skill, dict):
            continue
        tags = skill.get("tags", [])
        tags_text = ", ".join(str(tag) for tag in tags) if isinstance(tags, list) else ""
        description = str(skill.get("description") or skill.get("note") or "")
        used = "yes" if _project_is_linked(skill, project) else "no"
        print(
            f"{truncate(name, 22):<24}"
            f"{truncate(str(skill.get('version', '0.1.0')), 10):<12}"
            f"{used:<8}"
            f"{truncate(tags_text, 24):<26}"
            f"{truncate(description, 48)}"
        )
    return 0


def _skill_matches(skill: dict[str, Any], query: str) -> bool:
    source = skill.get("source", {})
    source_text = " ".join(str(value) for value in source.values()) if isinstance(source, dict) else ""
    parts = [
        skill.get("name", ""),
        skill.get("version", ""),
        skill.get("description", ""),
        skill.get("note", ""),
        " ".join(str(tag) for tag in skill.get("tags", []) if tag),
        source_text,
    ]
    return query.casefold() in "\n".join(str(part) for part in parts).casefold()


def command_search(args: argparse.Namespace) -> int:
    query = " ".join(args.query).strip()
    if not query:
        raise SkmError("Search query cannot be empty.")
    skills = load_registry()["skills"]
    matches = [
        skill
        for skill in skills.values()
        if isinstance(skill, dict) and _skill_matches(skill, query)
    ]
    matches.sort(key=lambda item: str(item.get("name", "")))
    if not matches:
        print(f"No skills found for: {query}")
        return 0
    print(f"Found {len(matches)} skill{'s' if len(matches) != 1 else ''}:")
    print()
    for index, skill in enumerate(matches, start=1):
        print(f"{index}. {skill.get('name', '')} ({skill.get('version', '0.1.0')})")
        description = skill.get("description") or skill.get("note")
        if description:
            print(f"   {description}")
        tags = skill.get("tags", [])
        if tags:
            print(f"   Tags: {', '.join(str(tag) for tag in tags)}")
    return 0


def command_info(args: argparse.Namespace) -> int:
    registry = load_registry()
    skill = require_skill(registry, args.name)
    source = skill_source_path(skill)
    print(f"Name: {skill.get('name', args.name)}")
    print(f"Version: {skill.get('version', '0.1.0')}")
    print(f"Description: {skill.get('description', '')}")
    print(f"Note: {skill.get('note', '')}")
    print(f"Tags: {', '.join(str(tag) for tag in skill.get('tags', []))}")
    print(f"Path: {source}")
    print(f"Entry: {skill.get('entry', source.name)}")
    source_info = skill.get("source")
    if isinstance(source_info, dict):
        print(f"Source: {source_info.get('type', '')} {source_info.get('location', '')}".rstrip())
    print()
    print("Projects:")
    links = skill.get("links", [])
    if isinstance(links, list) and links:
        for item in links:
            if isinstance(item, dict):
                print(
                    f"- {item.get('project', '')} "
                    f"[{item.get('target', 'default')}, {item.get('mode', 'symlink')}]"
                )
    else:
        legacy = skill.get("linked_projects", [])
        if isinstance(legacy, list) and legacy:
            for project in legacy:
                print(f"- {project} [legacy]")
        else:
            print("- none")
    print()
    print(f"Created: {skill.get('created_at', '')}")
    print(f"Updated: {skill.get('updated_at', '')}")
    return 0


def command_use(args: argparse.Namespace) -> int:
    record = use_skill(args.name, target_name=args.target, copy=args.copy)
    print("Skill is ready in the current project.")
    print()
    print(f"Skill: {args.name}")
    print(f"Target: {record['relative_path']}")
    print(f"Mode: {record['mode']}")
    return 0


def command_unuse(args: argparse.Namespace) -> int:
    records = unuse_skill(args.name, target_name=args.target, force=args.force)
    print("Skill removed from the current project.")
    print()
    print(f"Skill: {args.name}")
    for record in records:
        print(f"Target: {record.get('relative_path', '')}")
    return 0


def command_status(_args: argparse.Namespace) -> int:
    records = project_status()
    if not records:
        print("No managed skills are used in this project.")
        return 0
    print(f"{'NAME':<24}{'TARGET':<12}{'MODE':<10}{'STATE':<10}PATH")
    for item in records:
        print(
            f"{truncate(str(item['name']), 22):<24}"
            f"{truncate(str(item['target']), 10):<12}"
            f"{str(item['mode']):<10}"
            f"{str(item['state']):<10}"
            f"{item['path']}"
        )
    return 0


def command_sync(args: argparse.Namespace) -> int:
    records = sync_project_skills(args.name, force=args.force)
    if not records:
        print("No copy-mode skills need syncing in this project.")
        return 0
    for record in records:
        print(f"Synced {record['name']} -> {record['path']}")
    return 0


def command_remove(args: argparse.Namespace) -> int:
    path = remove_skill(args.name)
    print("Skill removed.")
    print()
    print(f"Name: {args.name}")
    print(f"Path: {path}")
    return 0


def _update_one(name: str) -> dict[str, Any]:
    registry = load_registry()
    skill = require_skill(registry, name)
    source_info = skill.get("source")
    if not isinstance(source_info, dict) or not isinstance(source_info.get("location"), str):
        raise SkmError(f"Skill has no update source: {name}")
    source_type = source_info.get("type")
    ref = source_info.get("ref") if isinstance(source_info.get("ref"), str) else None
    with prepare_source(
        source_info["location"],
        force_git=source_type == "git",
        ref=ref,
    ) as (source, metadata):
        metadata.pop("suggested_name", None)
        return update_local_skill(name, source, source_metadata=metadata)


def command_update(args: argparse.Namespace) -> int:
    names = [args.name] if args.name else sorted(load_registry()["skills"])
    if not names:
        print("No skills installed.")
        return 0
    failures = 0
    for name in names:
        try:
            record = _update_one(name)
            print(f"Updated {name} to {record.get('version', '0.1.0')}.")
        except SkmError as exc:
            if args.name:
                raise
            failures += 1
            print(f"Failed to update {name}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def command_pack(args: argparse.Namespace) -> int:
    output = pack_skill(
        args.name,
        Path(args.output) if args.output else None,
        force=args.force,
    )
    print("Skill package created.")
    print()
    print(f"Path: {output}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    issues = run_doctor(repair=args.repair)
    if not issues:
        print("Skill Manager is healthy.")
        return 0
    for issue in issues:
        suffix = " [repaired]" if issue.repaired else ""
        print(f"{issue.level.upper():<8} {issue.code}: {issue.message}{suffix}")
    remaining_errors = [
        issue for issue in issues if not issue.repaired and issue.level == "error"
    ]
    remaining_warnings = [issue for issue in issues if not issue.repaired]
    print()
    print(
        f"Found {len(issues)} issue(s); "
        f"{len([item for item in issues if item.repaired])} repaired."
    )
    return 1 if remaining_errors or (args.strict and remaining_warnings) else 0


def command_config(args: argparse.Namespace) -> int:
    config = load_config()
    if args.action is None:
        print(f"default_target = {config['default_target']}")
        print(f"link_mode = {config['link_mode']}")
        print("targets:")
        for name, path in sorted(config["targets"].items()):
            print(f"  {name} = {path}")
        return 0

    if args.key is None or args.value is None:
        raise SkmError("Usage: skm config set <key> <value>")
    key = args.key
    value = args.value
    if key == "link_mode":
        config["link_mode"] = value
    elif key == "default_target":
        config["default_target"] = value
    elif key.startswith("target.") and len(key) > len("target."):
        config["targets"][key[len("target.") :]] = value
    else:
        raise SkmError(
            "Unknown config key. Use link_mode, default_target, or target.<name>."
        )
    save_config(config)
    print(f"Updated {key} = {value}")
    return 0


def _add_metadata_arguments(parser: argparse.ArgumentParser, *, require_name: bool = False) -> None:
    parser.add_argument("--name", required=require_name, help="Skill name.")
    parser.add_argument("--version", help="Skill version.")
    parser.add_argument("--tags", help="Comma-separated tags.")
    parser.add_argument("--description", help="Short description.")
    parser.add_argument("--note", help="Human-friendly note.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skm",
        description="Create, install, share, and use local AI skills.",
    )
    parser.add_argument("--version", action="version", version=f"skm {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize local storage.")
    init_parser.set_defaults(func=command_init)

    create_parser = subparsers.add_parser("create", help="Create a new skill directory.")
    create_parser.add_argument("name")
    create_parser.add_argument("--path", help="Destination directory. Defaults to ./<name>.")
    create_parser.add_argument("--version", default="0.1.0")
    create_parser.add_argument("--tags")
    create_parser.add_argument("--description")
    create_parser.add_argument("--note")
    create_parser.add_argument("--author")
    create_parser.add_argument("--license")
    create_parser.set_defaults(func=command_create)

    add_parser = subparsers.add_parser("add", help="Install a Markdown file or skill directory.")
    add_parser.add_argument("source")
    _add_metadata_arguments(add_parser)
    add_parser.add_argument("--git", action="store_true", help="Treat the source as a Git repository.")
    add_parser.add_argument("--ref", help="Git branch or tag.")
    add_parser.set_defaults(func=command_add)

    list_parser = subparsers.add_parser("list", aliases=["ls"], help="List installed skills.")
    list_parser.set_defaults(func=command_list)

    search_parser = subparsers.add_parser("search", help="Search installed skills.")
    search_parser.add_argument("query", nargs="+")
    search_parser.set_defaults(func=command_search)

    info_parser = subparsers.add_parser("info", aliases=["show"], help="Show skill details.")
    info_parser.add_argument("name")
    info_parser.set_defaults(func=command_info)

    use_parser = subparsers.add_parser("use", help="Place a skill in the current project.")
    use_parser.add_argument("name")
    use_parser.add_argument("--target", help="Configured target, such as codex or claude.")
    use_parser.add_argument("--copy", action="store_true")
    use_parser.set_defaults(func=command_use)

    unuse_parser = subparsers.add_parser("unuse", help="Remove a skill from the current project.")
    unuse_parser.add_argument("name")
    unuse_parser.add_argument("--target")
    unuse_parser.add_argument("--force", action="store_true", help="Remove a locally modified copy.")
    unuse_parser.set_defaults(func=command_unuse)

    status_parser = subparsers.add_parser("status", help="Show skills used by this project.")
    status_parser.set_defaults(func=command_status)

    sync_parser = subparsers.add_parser("sync", help="Refresh copy-mode skills in this project.")
    sync_parser.add_argument("name", nargs="?")
    sync_parser.add_argument("--force", action="store_true", help="Replace locally modified copies.")
    sync_parser.set_defaults(func=command_sync)

    remove_parser = subparsers.add_parser("remove", aliases=["rm"], help="Uninstall a skill.")
    remove_parser.add_argument("name")
    remove_parser.set_defaults(func=command_remove)

    update_parser = subparsers.add_parser("update", help="Refresh skills from their sources.")
    update_parser.add_argument("name", nargs="?")
    update_parser.set_defaults(func=command_update)

    pack_parser = subparsers.add_parser("pack", help="Create a shareable ZIP package.")
    pack_parser.add_argument("name")
    pack_parser.add_argument("--output", "-o")
    pack_parser.add_argument("--force", action="store_true")
    pack_parser.set_defaults(func=command_pack)

    doctor_parser = subparsers.add_parser("doctor", help="Check storage and project link health.")
    doctor_parser.add_argument("--repair", action="store_true", help="Prune missing link records.")
    doctor_parser.add_argument("--strict", action="store_true", help="Treat warnings as errors.")
    doctor_parser.set_defaults(func=command_doctor)

    config_parser = subparsers.add_parser("config", help="Show or update simple configuration.")
    config_parser.add_argument("action", nargs="?", choices=["set"])
    config_parser.add_argument("key", nargs="?")
    config_parser.add_argument("value", nargs="?")
    config_parser.set_defaults(func=command_config)

    # Original MVP commands remain available for existing users.
    register_parser = subparsers.add_parser("register", help="Compatibility alias for add.")
    register_parser.add_argument("file")
    _add_metadata_arguments(register_parser, require_name=True)
    register_parser.set_defaults(func=command_register)

    link_parser = subparsers.add_parser("link", help="Compatibility alias for use.")
    link_parser.add_argument("name")
    link_parser.add_argument("--target")
    link_parser.add_argument("--copy", action="store_true")
    link_parser.set_defaults(func=command_use)

    unlink_parser = subparsers.add_parser("unlink", help="Compatibility alias for unuse.")
    unlink_parser.add_argument("name")
    unlink_parser.add_argument("--target")
    unlink_parser.add_argument("--force", action="store_true")
    unlink_parser.set_defaults(func=command_unuse)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SkmError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"Operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
