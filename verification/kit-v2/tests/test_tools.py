"""Read-only tool contracts using temporary fixtures; no product imports or PTYs."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
from tools import verify_bundle as verify
from tools import scope_guard as scope
from tools import conformance


def tempdir():
    base = os.environ.get("SMARTCLI_V2_TEST_TMP")
    if not base or not Path(base).is_dir():
        raise RuntimeError("Set SMARTCLI_V2_TEST_TMP to an existing approved RUN directory before tool tests")
    if Path(base).resolve().is_relative_to(KIT):
        raise RuntimeError("Tool-test temporary files must be outside the delivery package")
    return tempfile.TemporaryDirectory(dir=base)


def make_bundle(root, extra=None):
    files = {"README.md": b"fixture\n", "agents/openai.yaml": b"display_name: fixture\n"}
    files.update(extra or {})
    for name, raw in files.items():
        p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
    manifest = {"schema_version": 2, "files": {n: hashlib.sha256(raw).hexdigest() for n, raw in files.items()}}
    (root / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def zip_bundle(root, dest):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in root.rglob("*"):
            if p.is_file(): z.write(p, "bundle/" + p.relative_to(root).as_posix())


class IntegrityTests(unittest.TestCase):
    def test_directory_pass(self):
        with tempdir() as td:
            root = Path(td); make_bundle(root)
            self.assertTrue(verify.verify_directory(root)["ok"])

    def test_yaml_tampering_fails(self):
        with tempdir() as td:
            root = Path(td); make_bundle(root)
            (root / "agents/openai.yaml").write_bytes(b"display_name: modified\n")
            r = verify.verify_directory(root)
            self.assertFalse(r["ok"])
            self.assertEqual(r["mismatches"][0]["path"], "agents/openai.yaml")

    def test_extra_file_fails(self):
        with tempdir() as td:
            root = Path(td); make_bundle(root); (root / "extra.json").write_bytes(b"{}")
            self.assertFalse(verify.verify_directory(root)["ok"])

    def test_missing_file_fails(self):
        with tempdir() as td:
            root = Path(td); make_bundle(root); (root / "README.md").unlink()
            self.assertFalse(verify.verify_directory(root)["ok"])

    def test_interpreter_cache_ignored(self):
        with tempdir() as td:
            root = Path(td); make_bundle(root); (root / "__pycache__").mkdir()
            (root / "__pycache__/test.pyc").write_bytes(b"cache")
            self.assertTrue(verify.verify_directory(root)["ok"])

    def test_duplicate_manifest_key_rejected(self):
        with self.assertRaises(ValueError):
            verify._json(b'{"schema_version":2,"files":{"x":"a","x":"b"}}')

    def test_bad_paths_rejected(self):
        for name in ["/abs", "../escape", "a/../b", "a\\b", "C:/x", "a//b", "./a"]:
            with self.subTest(name=name), self.assertRaises(ValueError): verify._safe(name)

    def test_zip_pass_and_metadata_tamper(self):
        with tempdir() as td:
            root = Path(td) / "root"; root.mkdir(); make_bundle(root)
            dest = Path(td) / "good.zip"; zip_bundle(root, dest)
            self.assertTrue(verify.verify_zip(dest)["ok"])
            (root / "agents/openai.yaml").write_bytes(b"changed")
            zip_bundle(root, Path(td) / "bad.zip")
            self.assertFalse(verify.verify_zip(Path(td) / "bad.zip")["ok"])

    def test_duplicate_zip_entry_rejected(self):
        with tempdir() as td:
            dest = Path(td) / "bad.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(dest, "w") as z:
                    z.writestr("bundle/x", "a"); z.writestr("bundle/x", "b")
            with self.assertRaises(ValueError): verify.verify_zip(dest)

    def test_zip_escape_rejected(self):
        with tempdir() as td:
            dest = Path(td) / "bad.zip"
            with zipfile.ZipFile(dest, "w") as z: z.writestr("../outside", "a")
            with self.assertRaises(ValueError): verify.verify_zip(dest)

    def test_zip_symlink_rejected(self):
        with tempdir() as td:
            dest = Path(td) / "bad.zip"
            info = zipfile.ZipInfo("bundle/link"); info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(dest, "w") as z: z.writestr(info, "outside")
            with self.assertRaises(ValueError): verify.verify_zip(dest)

    def test_directory_symlink_rejected_when_permitted(self):
        with tempdir() as td:
            root = Path(td); make_bundle(root)
            try: (root / "link").symlink_to(root / "README.md")
            except OSError as exc: self.skipTest(f"symlink creation unavailable: {exc}")
            with self.assertRaises(ValueError): verify.verify_directory(root)

    def test_integrity_is_not_authentication(self):
        with tempdir() as td:
            root = Path(td); make_bundle(root)
            self.assertEqual(verify.verify_directory(root)["authentication"], "NOT_PROVIDED")


class ScopeTests(unittest.TestCase):
    def snapshot(self, files, head="abc"):
        return {"repo": "fixture", "head": head, "files": files}
    def policy(self): return {"max_changed_files": 1, "allow_paths": ["core.py"]}

    def test_preexisting_dirty_file_not_counted_again(self):
        a = self.snapshot({"prior.py": "dirty-existing", "core.py": "old"})
        b = self.snapshot({"prior.py": "dirty-existing", "core.py": "new"})
        self.assertTrue(scope.compare(a, b, self.policy())["ok"])

    def test_extra_change_rejected(self):
        a = self.snapshot({"core.py": "old"}); b = self.snapshot({"core.py": "new", "config.yml": "new"})
        r = scope.compare(a, b, self.policy())
        self.assertFalse(r["ok"]); self.assertIn("config.yml", r["outside_scope"])

    def test_maximum_touch_rejected(self):
        a = self.snapshot({"core.py": "old"}); b = self.snapshot({"core.py": "new"})
        self.assertFalse(scope.compare(a, b, {"max_changed_files": 0, "allow_paths": ["core.py"]})["ok"])

    def test_commit_rejected(self):
        self.assertFalse(scope.compare(self.snapshot({}), self.snapshot({}, "new"), self.policy())["ok"])

    def test_other_repository_rejected(self):
        a = self.snapshot({}); b = self.snapshot({}); b["repo"] = "elsewhere"
        with self.assertRaises(ValueError): scope.compare(a, b, self.policy())

    def test_deletion_is_a_change(self):
        a = self.snapshot({"core.py": "old"}); b = self.snapshot({"core.py": None})
        self.assertEqual(scope.compare(a, b, self.policy())["changed_files"], ["core.py"])

    def test_report_does_not_overwrite(self):
        with tempdir() as td:
            root = Path(td); repo = root / "repo"; repo.mkdir(); dest = root / "report.json"
            scope.write_new(dest, {"ok": True}, repo)
            with self.assertRaises(ValueError): scope.write_new(dest, {}, repo)
            with self.assertRaises(ValueError): scope.write_new(repo / "bad.json", {}, repo)


class RunnerTests(unittest.TestCase):
    def test_stdout_and_stderr_collected(self):
        r = conformance.run_bounded([sys.executable, "-c", "import sys;print('out');print('err',file=sys.stderr)"], 3)
        self.assertEqual(r["returncode"], 0)
        self.assertIn("out", r["stdout"]); self.assertIn("err", r["stderr"])

    def test_timeout_not_pass(self):
        r = conformance.run_bounded([sys.executable, "-c", "import time;time.sleep(3)"], 0.05)
        self.assertTrue(r["timed_out"]); self.assertNotEqual(r["returncode"], 0)

    def test_output_is_bounded(self):
        r = conformance.run_bounded([sys.executable, "-c", "import sys;sys.stdout.write('x'*600000);sys.stdout.flush()"], 3)
        self.assertTrue(r["output_limited"])
        self.assertLessEqual(len(r["stdout"].encode()) + len(r["stderr"].encode()), conformance.MAX_OUTPUT)

    def test_execution_consent_required(self):
        r = subprocess.run([sys.executable, "-B", str(KIT / "tools/conformance.py"), "--repo", str(KIT)],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(r.returncode, 2); self.assertIn("consent", r.stderr)

    def test_missing_dependency_is_not_run(self):
        with tempdir() as td:
            repo = Path(td) / "repo"; core = repo / "smartcli_core"; core.mkdir(parents=True)
            (core / "screen_model.py").write_text("", encoding="utf-8")
            (core / "__init__.py").write_text("raise ModuleNotFoundError('missing-test-fixture-dependency')\n", encoding="utf-8")
            r = subprocess.run([sys.executable, "-B", str(KIT / "tools/conformance.py"), "--repo", str(repo),
                "--case", "screen", "--consent-execute-reviewed-code"], capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 2)
            records = [json.loads(line) for line in r.stdout.splitlines()]
            self.assertEqual(records[0]["status"], "NOT_RUN")
            self.assertFalse(records[-1]["summary"]["all_selected_pass"])

if __name__ == "__main__": unittest.main()
