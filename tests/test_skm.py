from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from skm.doctor import run_doctor
from skm.errors import SkmError
from skm.project_ops import project_status, sync_project_skills, unuse_skill, use_skill
from skm.sharing import pack_skill
from skm.skill_ops import add_local_skill, create_skill, remove_skill, update_local_skill
from skm.sources import prepare_source
from skm.storage import (
    config_path,
    init_storage,
    load_config,
    load_registry,
    registry_path,
    skill_source_path,
    skm_home,
    write_json_atomic,
)


class SkmTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="skbro-test-")
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.workspace = self.root / "workspace"
        self.project = self.root / "project"
        self.workspace.mkdir()
        self.project.mkdir()
        self.previous_cwd = Path.cwd()
        self.environment = patch.dict(os.environ, {"SKBRO_HOME": str(self.home)})
        self.environment.start()

    def tearDown(self) -> None:
        os.chdir(self.previous_cwd)
        self.environment.stop()
        self.temp.cleanup()

    def make_skill(self, name: str = "demo", version: str = "0.1.0") -> Path:
        path = self.workspace / name
        create_skill(name, path, version=version, description="Demo skill", tags="demo,test")
        return path

    def test_directory_skill_lifecycle_in_copy_mode(self) -> None:
        source = self.make_skill()
        record = add_local_skill(source)
        self.assertEqual(record["name"], "demo")
        self.assertTrue(skill_source_path(record).is_dir())

        use = use_skill("demo", copy=True, project=self.project)
        target = self.project / use["relative_path"]
        self.assertTrue((target / "SKILL.md").is_file())
        self.assertEqual(project_status(self.project)[0]["state"], "ok")

        with self.assertRaises(SkmError):
            remove_skill("demo")

        unuse_skill("demo", project=self.project)
        self.assertFalse(target.exists())
        removed = remove_skill("demo")
        self.assertFalse(removed.exists())

    def test_markdown_source_is_normalized_to_skill_directory(self) -> None:
        markdown = self.workspace / "writer.md"
        markdown.write_text("# Writer\n", encoding="utf-8")
        record = add_local_skill(markdown, tags="writing,writing")
        installed = skill_source_path(record)
        self.assertEqual(record["name"], "writer")
        self.assertEqual(record["tags"], ["writing"])
        self.assertEqual((installed / "SKILL.md").read_text(encoding="utf-8"), "# Writer\n")
        self.assertTrue((installed / "skill.json").is_file())

    def test_pack_can_be_installed_again(self) -> None:
        source = self.make_skill("shareable", "1.2.0")
        add_local_skill(source)
        bundle = pack_skill("shareable", self.workspace / "shareable.zip")
        remove_skill("shareable")

        with prepare_source(str(bundle)) as (prepared, metadata):
            metadata.pop("suggested_name", None)
            record = add_local_skill(prepared, source_metadata=metadata)
        self.assertEqual(record["name"], "shareable")
        self.assertEqual(record["version"], "1.2.0")
        self.assertEqual(record["source"]["type"], "zip")

    def test_zip_can_be_installed_from_http_url(self) -> None:
        source = self.make_skill("remote-demo")
        add_local_skill(source)
        bundle = pack_skill("remote-demo", self.workspace / "remote-demo.zip")
        remove_skill("remote-demo")

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, _format: str, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            partial(QuietHandler, directory=str(self.workspace)),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/{bundle.name}"
            with prepare_source(url) as (prepared, metadata):
                metadata.pop("suggested_name", None)
                record = add_local_skill(prepared, source_metadata=metadata)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        self.assertEqual(record["name"], "remote-demo")
        self.assertEqual(record["source"]["type"], "url")

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_skill_can_be_installed_from_git(self) -> None:
        repo = self.make_skill("git-demo")
        subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "skm-test@example.com"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "SKM Test"], cwd=repo, check=True
        )
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "initial"], cwd=repo, check=True
        )

        with prepare_source(repo.as_uri(), force_git=True) as (prepared, metadata):
            metadata.pop("suggested_name", None)
            record = add_local_skill(prepared, source_metadata=metadata)
        self.assertEqual(record["name"], "git-demo")
        self.assertEqual(record["source"]["type"], "git")

    def test_update_marks_copy_outdated_and_sync_refreshes_it(self) -> None:
        source = self.make_skill("syncable")
        add_local_skill(source)
        use_skill("syncable", copy=True, project=self.project)

        (source / "SKILL.md").write_text("# Updated\n", encoding="utf-8")
        update_local_skill(
            "syncable",
            source,
            source_metadata={"type": "local", "location": str(source)},
        )
        self.assertEqual(project_status(self.project)[0]["state"], "outdated")
        synced = sync_project_skills("syncable", project=self.project)
        self.assertEqual(synced[0]["name"], "syncable")
        self.assertEqual(project_status(self.project)[0]["state"], "ok")

    def test_modified_project_copy_requires_force(self) -> None:
        source = self.make_skill("modified-demo")
        add_local_skill(source)
        record = use_skill("modified-demo", copy=True, project=self.project)
        target = self.project / record["relative_path"]
        (target / "SKILL.md").write_text("# Local changes\n", encoding="utf-8")

        self.assertEqual(project_status(self.project)[0]["state"], "modified")
        with self.assertRaisesRegex(SkmError, "was modified"):
            sync_project_skills("modified-demo", project=self.project)
        with self.assertRaisesRegex(SkmError, "was modified"):
            unuse_skill("modified-demo", project=self.project)

        sync_project_skills("modified-demo", project=self.project, force=True)
        self.assertEqual(project_status(self.project)[0]["state"], "ok")
        (target / "SKILL.md").write_text("# More local changes\n", encoding="utf-8")
        unuse_skill("modified-demo", project=self.project, force=True)
        self.assertFalse(target.exists())

    def test_doctor_repairs_missing_link_record(self) -> None:
        source = self.make_skill("doctor-demo")
        add_local_skill(source)
        record = use_skill("doctor-demo", copy=True, project=self.project)
        shutil.rmtree(self.project / record["relative_path"])

        issues = run_doctor(repair=True)
        missing = [item for item in issues if item.code == "missing-link"]
        self.assertEqual(len(missing), 1)
        self.assertTrue(missing[0].repaired)
        self.assertEqual(load_registry()["skills"]["doctor-demo"]["links"], [])

    def test_invalid_config_shapes_and_escaping_targets_are_rejected(self) -> None:
        init_storage()
        config_path().write_text("[]\n", encoding="utf-8")
        with self.assertRaisesRegex(SkmError, "Expected a JSON object"):
            load_config()

        write_json_atomic(
            config_path(),
            {
                "schema_version": 1,
                "default_target": "default",
                "link_mode": "copy",
                "targets": {"default": "../outside"},
            },
        )
        with self.assertRaisesRegex(SkmError, "inside the project"):
            load_config()

    def test_legacy_skm_home_environment_variable_still_works(self) -> None:
        legacy_home = self.root / "legacy-home"
        with patch.dict(
            os.environ,
            {"SKBRO_HOME": "", "SKM_HOME": str(legacy_home)},
        ):
            self.assertEqual(skm_home(), legacy_home.resolve())

    def test_registry_cannot_reference_files_outside_home(self) -> None:
        init_storage()
        outside = self.root / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        registry = {
            "schema_version": 2,
            "skills": {
                "unsafe": {
                    "name": "unsafe",
                    "path": "../outside.md",
                }
            },
        }
        write_json_atomic(registry_path(), registry)
        skill = load_registry()["skills"]["unsafe"]
        with self.assertRaisesRegex(SkmError, "outside SKBro home"):
            skill_source_path(skill)

    def test_original_single_file_registry_remains_usable(self) -> None:
        init_storage()
        legacy_dir = self.home / "registry"
        legacy_file = legacy_dir / "legacy.md"
        legacy_file.write_text("# Legacy\n", encoding="utf-8")
        write_json_atomic(
            registry_path(),
            {
                "skills": {
                    "legacy": {
                        "name": "legacy",
                        "file": "registry/legacy.md",
                        "description": "Old format",
                        "tags": ["legacy"],
                        "linked_projects": [],
                    }
                }
            },
        )

        record = use_skill("legacy", copy=True, project=self.project)
        self.assertEqual(record["relative_path"], str(Path(".skills") / "legacy.md"))
        self.assertTrue((self.project / record["relative_path"]).is_file())
        unuse_skill("legacy", project=self.project)
        self.assertFalse((self.project / record["relative_path"]).exists())

    def test_zip_path_traversal_is_rejected(self) -> None:
        archive = self.workspace / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../outside.txt", "bad")
        with self.assertRaisesRegex(SkmError, "Unsafe path"):
            with prepare_source(str(archive)):
                pass


if __name__ == "__main__":
    unittest.main()
