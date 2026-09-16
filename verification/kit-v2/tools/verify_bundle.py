#!/usr/bin/env python3
"""Read-only SHA256 verification for this directory or its final ZIP.

Rejects omitted/extra files, symlinks, duplicate ZIP names and unsafe paths.
Integrity is not publisher authentication. No install, extraction or network.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

MANIFEST = "MANIFEST.json"
MAX_BYTES = 64 * 1024 * 1024


def _safe(name: str) -> None:
    p = PurePosixPath(name)
    if not name or p.is_absolute() or "\\" in name or ":" in name:
        raise ValueError(f"unsafe path: {name!r}")
    if any(part in {"", ".", ".."} for part in name.split("/")):
        raise ValueError(f"unsafe path: {name!r}")


def _json(raw: bytes) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    data = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        raise ValueError("expected v2 manifest")
    entries = data.get("files")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("manifest has no file inventory")
    for name, digest in entries.items():
        _safe(name)
        if name == MANIFEST or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid manifest entry")
    return data


def _ignored(name: str) -> bool:
    # Only interpreter cache is ignored. YAML, metadata and all other files count.
    return "__pycache__" in PurePosixPath(name).parts or name.endswith((".pyc", ".pyo"))


def _compare(entries: dict, contents: dict[str, bytes]) -> dict:
    expected = set(entries)
    actual = set(contents)
    problems = [{"path": p, "reason": "missing"} for p in sorted(expected - actual)]
    problems += [{"path": p, "reason": "unlisted"} for p in sorted(actual - expected)]
    for name in sorted(expected & actual):
        digest = hashlib.sha256(contents[name]).hexdigest()
        if digest != entries[name]:
            problems.append({"path": name, "reason": "sha256_mismatch", "expected": entries[name], "actual": digest})
    return {"ok": not problems, "checked_files": len(expected & actual), "mismatches": problems,
            "authentication": "NOT_PROVIDED"}


def verify_directory(root: Path) -> dict:
    if root.is_symlink():
        raise ValueError("root symlink not permitted")
    root = root.resolve(strict=True)
    paths = []
    total = 0
    for p in root.rglob("*"):
        if p.is_symlink():
            raise ValueError(f"symlink not permitted: {p.relative_to(root)}")
        if p.is_file() and not _ignored(p.relative_to(root).as_posix()):
            total += p.stat().st_size
            if total > MAX_BYTES:
                raise ValueError("bundle exceeds verification size budget")
            paths.append(p)
    data = _json((root / MANIFEST).read_bytes())
    contents = {p.relative_to(root).as_posix(): p.read_bytes() for p in paths if p != root / MANIFEST}
    return _compare(data["files"], contents)


def verify_zip(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        names = [i.filename for i in z.infolist() if not i.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP entry")
        if sum(i.file_size for i in z.infolist()) > MAX_BYTES:
            raise ValueError("ZIP exceeds size budget")
        for i in z.infolist():
            _safe(i.filename.rstrip("/"))
            if stat.S_ISLNK(i.external_attr >> 16):
                raise ValueError("ZIP contains symlink")
        manifest_names = [n for n in names if len(PurePosixPath(n).parts) == 2 and n.endswith("/" + MANIFEST)]
        if len(manifest_names) != 1:
            raise ValueError("expected one root-folder manifest")
        prefix = manifest_names[0].rsplit("/", 1)[0] + "/"
        if any(not n.startswith(prefix) for n in names):
            raise ValueError("ZIP has entries outside the root folder")
        data = _json(z.read(manifest_names[0]))
        contents = {n[len(prefix):]: z.read(n) for n in names
                    if n != manifest_names[0] and not _ignored(n[len(prefix):])}
        return _compare(data["files"], contents)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--zip", type=Path)
    args = ap.parse_args()
    try:
        result = verify_zip(args.zip) if args.zip else verify_directory(args.root)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1

if __name__ == "__main__":
    sys.exit(main())
