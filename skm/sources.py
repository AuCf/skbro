from __future__ import annotations

import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .errors import SkmError


MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def _is_url(value: str) -> bool:
    return urllib.parse.urlparse(value).scheme in {"http", "https"}


def _looks_like_git(value: str) -> bool:
    lowered = value.lower().rstrip("/")
    if lowered.endswith(".git") or value.startswith("git@"):
        return True
    if not _is_url(value):
        return False
    parsed = urllib.parse.urlparse(value)
    return (
        parsed.netloc.lower() in {"github.com", "gitlab.com", "bitbucket.org"}
        and not lowered.endswith((".zip", ".md"))
    )


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "skbro/0.3"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length:
                try:
                    too_large = int(length) > MAX_DOWNLOAD_BYTES
                except ValueError:
                    too_large = False
                if too_large:
                    raise SkmError("Remote skill is larger than the 100 MB download limit.")
            total = 0
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise SkmError(
                            "Remote skill is larger than the 100 MB download limit."
                        )
                    output.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SkmError(f"Failed to download skill: {url}\nReason: {exc}") from exc


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                normalized = item.filename.replace("\\", "/")
                relative = Path(normalized)
                if relative.is_absolute() or ".." in relative.parts:
                    raise SkmError(f"Unsafe path in ZIP archive: {item.filename}")
                unix_mode = item.external_attr >> 16
                if unix_mode and (unix_mode & 0o170000) == 0o120000:
                    raise SkmError(f"ZIP archive contains a symbolic link: {item.filename}")
                target = (destination / relative).resolve()
                try:
                    target.relative_to(destination.resolve())
                except ValueError as exc:
                    raise SkmError(f"Unsafe path in ZIP archive: {item.filename}") from exc
            bundle.extractall(destination)
    except zipfile.BadZipFile as exc:
        raise SkmError(f"Invalid ZIP archive: {archive}") from exc


def _find_skill_root(extracted: Path) -> Path:
    if (extracted / "SKILL.md").is_file() or (extracted / "skill.json").is_file():
        return extracted
    children = [
        child
        for child in extracted.iterdir()
        if child.is_dir() and child.name not in {"__MACOSX", ".git"}
    ]
    candidates = [
        child
        for child in children
        if (child / "SKILL.md").is_file() or (child / "skill.json").is_file()
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise SkmError("Could not find a skill at the root of the ZIP or Git repository.")


def _clone_git(url: str, destination: Path, ref: str | None) -> None:
    git = shutil.which("git")
    if git is None:
        raise SkmError("Git is required to install this source, but it was not found.")
    command = [git, "clone", "--depth", "1"]
    if ref:
        command.extend(["--branch", ref])
    command.extend([url, str(destination)])
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SkmError(f"Failed to clone Git skill: {url}\nReason: {exc}") from exc
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "git clone failed"
        raise SkmError(f"Failed to clone Git skill: {url}\nReason: {reason}")


@contextmanager
def prepare_source(
    source: str,
    *,
    force_git: bool = False,
    ref: str | None = None,
) -> Iterator[tuple[Path, dict[str, Any]]]:
    local = Path(source).expanduser()
    if local.exists():
        resolved = local.resolve()
        if resolved.is_dir() or resolved.suffix.lower() == ".md":
            yield resolved, {"type": "local", "location": str(resolved)}
            return
        if resolved.is_file() and resolved.suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory(prefix="skbro-zip-") as temp:
                extracted = Path(temp) / "content"
                extracted.mkdir()
                _safe_extract_zip(resolved, extracted)
                yield _find_skill_root(extracted), {
                    "type": "zip",
                    "location": str(resolved),
                    "suggested_name": resolved.stem,
                }
                return
        raise SkmError(f"Unsupported local skill source: {resolved}")

    if force_git or _looks_like_git(source):
        with tempfile.TemporaryDirectory(prefix="skbro-git-") as temp:
            checkout = Path(temp) / "checkout"
            _clone_git(source, checkout, ref)
            root = _find_skill_root(checkout)
            metadata: dict[str, Any] = {"type": "git", "location": source}
            repo_name = Path(urllib.parse.urlparse(source).path).stem
            if repo_name:
                metadata["suggested_name"] = repo_name
            if ref:
                metadata["ref"] = ref
            yield root, metadata
            return

    if _is_url(source):
        parsed = urllib.parse.urlparse(source)
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in {".zip", ".md"}:
            raise SkmError("Remote sources must be a Markdown file, ZIP archive, or Git URL.")
        with tempfile.TemporaryDirectory(prefix="skbro-url-") as temp:
            downloaded = Path(temp) / f"download{suffix}"
            _download(source, downloaded)
            if suffix == ".md":
                yield downloaded, {
                    "type": "url",
                    "location": source,
                    "suggested_name": Path(parsed.path).stem,
                }
            else:
                extracted = Path(temp) / "content"
                extracted.mkdir()
                _safe_extract_zip(downloaded, extracted)
                yield _find_skill_root(extracted), {
                    "type": "url",
                    "location": source,
                    "format": "zip",
                    "suggested_name": Path(parsed.path).stem,
                }
            return

    raise SkmError(f"Source not found: {source}")
