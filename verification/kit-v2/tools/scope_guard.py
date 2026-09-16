#!/usr/bin/env python3
"""Capture/check working-file fingerprints against a worker's exact allowlist.
Read-only toward the repo. Reports are explicit, new paths outside repo/kit.
This is change-surface auditing, not filesystem confinement or a sandbox.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

KIT = Path(__file__).resolve().parents[1]
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024


def git(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=15)
    if proc.returncode:
        raise ValueError(proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout


def capture(repo: Path) -> dict:
    repo = repo.resolve(strict=True)
    top = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel")).strip()).resolve()
    if top != repo: raise ValueError("repo must be the exact Git top level")
    names = set(git(repo, "ls-files", "-z").split(b"\0"))
    names.update(git(repo, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0"))
    files = {}; size = 0
    for raw in sorted(names - {b""}):
        name = os.fsdecode(raw); p = repo / name
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
            raise ValueError("unsafe Git path")
        if p.is_symlink(): raise ValueError(f"symlink requires manual review: {name}")
        if not p.exists(): files[name] = None; continue
        if not p.is_file() or not p.resolve().is_relative_to(repo):
            raise ValueError(f"non-file or escaping path requires review: {name}")
        n = p.stat().st_size; size += n
        if n > MAX_FILE or size > MAX_TOTAL:
            raise ValueError("fingerprint budget exceeded; do not silently skip files")
        files[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"schema_version": 2, "repo": str(repo), "head": git(repo, "rev-parse", "HEAD").decode().strip(),
            "files": files, "excluded": "gitignored files, including .codegraph; outside-repo files"}


def compare(before: dict, after: dict, scope: dict) -> dict:
    if before.get("repo") != after.get("repo"):
        raise ValueError("snapshot belongs to another repo")
    changed = sorted(k for k in set(before["files"]) | set(after["files"])
                     if before["files"].get(k) != after["files"].get(k))
    # Missing -> absent tracked paths do not have a new fingerprint, but a real
    # deletion from a previously present file is detected above.
    outside = sorted(set(changed) - set(scope["allow_paths"]))
    head_changed = before["head"] != after["head"]
    ok = not outside and len(changed) <= scope["max_changed_files"] and not head_changed
    return {"ok": ok, "changed_files": changed, "outside_scope": outside,
            "max_changed_files": scope["max_changed_files"], "head_changed": head_changed,
            "limitations": "Ignored/outside-repo files and semantic correctness are not audited."}


def write_new(path: Path, data: dict, repo: Path) -> None:
    resolved = path.resolve()
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise ValueError("output must be a new file in an existing directory")
    if resolved.is_relative_to(repo.resolve()) or resolved.is_relative_to(KIT):
        raise ValueError("output must be outside the repo and kit")
    with path.open("x", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.write("\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["capture", "check"])
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--brief", choices=["T05", "T04", "T03", "A04-P"])
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    try:
        current = capture(a.repo)
        if a.action == "capture":
            if not a.out: raise ValueError("capture requires --out")
            write_new(a.out, current, a.repo)
            result = {"ok": True, "baseline": str(a.out), "tracked_and_untracked_files": len(current["files"])}
        else:
            if not a.baseline or not a.brief: raise ValueError("check requires --baseline and --brief")
            before = json.loads(a.baseline.read_text(encoding="utf-8"))
            scopes = json.loads((KIT / "data/scopes.json").read_text(encoding="utf-8"))
            result = compare(before, current, scopes[a.brief])
            if a.out: write_new(a.out, result, a.repo)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1

if __name__ == "__main__":
    sys.exit(main())
