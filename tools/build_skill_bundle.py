#!/usr/bin/env python3
"""build_skill_bundle.py — pack the three skills into one drop-in zip for a Release.

WHY THIS EXISTS
---------------
Installing the skills had two paths and both ask something of the user:
`/plugin marketplace add dwgx/SmartCLI` requires trusting a marketplace entry, and
cloning the repo requires git plus knowing which subdirectories matter. A single zip
attached to the GitHub Release is the third path: download, unzip into
`~/.claude/skills/`, done. No git, no pip, no marketplace.

That works only because every skill is self-contained, which is a real property of
this repo rather than an assumption:
  * `cmd-art` and `tui-ui` import nothing outside their own directory (pure stdlib).
  * `drive-tui` carries `_vendor/smartcli_core/`, a byte-identical copy of the core
    (enforced by `tests/test_vendor_sync.py`), and `smartcli_bootstrap.locate_core()`
    falls back to it when the real package is not installed.
So the zip is genuinely runnable on a machine with only CPython.

WHAT IT DELIBERATELY EXCLUDES
-----------------------------
`__pycache__`/`*.pyc` (158 files in a working tree — they are build artifacts, they
bloat the download, and a `.pyc` compiled by a different CPython is useless to the
recipient), plus OS noise like `.DS_Store`.

USAGE
    python tools/build_skill_bundle.py                  # -> dist/smartcli-skills-<ver>.zip
    python tools/build_skill_bundle.py --out /tmp       # elsewhere
    python tools/build_skill_bundle.py --verify-only    # check an existing zip

The version comes from `pyproject.toml`, so the artifact name cannot drift from the
release it belongs to.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("cmd-art", "drive-tui", "tui-ui")

#: Excluded from the archive. Build artifacts and OS noise only — never source.
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db"}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass


def version() -> str:
    """Read the version with a regex, not tomllib.

    tomllib is stdlib only from 3.11 while this project supports 3.10 — a tool that
    cannot run on the floor the project claims is a defect this repo has shipped
    before. `tests/test_version_sync.py` uses regexes for the same reason.
    """
    m = re.search(r'^version\s*=\s*"([^"]+)"',
                  (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit("error: could not read version from pyproject.toml")
    return m.group(1)


def wanted(path: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return False
    if path.suffix in EXCLUDE_SUFFIXES or path.name in EXCLUDE_NAMES:
        return False
    return path.is_file()


def build(out_dir: Path) -> Path:
    ver = version()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"smartcli-skills-{ver}.zip"

    files: list[tuple[Path, str]] = []
    for skill in SKILLS:
        base = ROOT / "skills" / skill
        if not base.is_dir():
            raise SystemExit(f"error: missing skill directory {base}")
        for p in sorted(base.rglob("*")):
            if wanted(p):
                # Archive paths are `<skill>/...` so unzipping INTO ~/.claude/skills/
                # lands each skill as its own directory, which is exactly the layout
                # Claude Code discovers.
                files.append((p, str(p.relative_to(ROOT / "skills"))))

    # A README at the archive root, because a bare zip of three folders does not say
    # where to put them.
    readme = f"""SmartCLI — three terminal Agent Skills (v{ver})

INSTALL (global, all projects):
    unzip smartcli-skills-{ver}.zip -d ~/.claude/skills/

INSTALL (one project only):
    unzip smartcli-skills-{ver}.zip -d <your-project>/.claude/skills/

That is the whole install. Restart is not required; skills are picked up per session.

WHAT YOU GET
    cmd-art     terminal visual effects + ASCII art (30 effects, 8 themes)
    drive-tui   drive real interactive TUIs — vim, htop, lazygit — by reading the
                screen as a cell grid instead of a byte stream
    tui-ui      cell-accurate terminal layout engine + 17 widgets

REQUIREMENTS — two of the three need nothing, one needs a pip install

    cmd-art     CPython 3.10+ and NOTHING else. Verified on a bare venv: all 30
    tui-ui      effects and all 17 widgets load with no third-party package.

    drive-tui   needs `pyte`:
                    pip install smartcli-toolkit

                The bundled `_vendor/smartcli_core/` means you do not need the
                smartcli_core *library* installed — but pyte is a third-party
                dependency of that library and is NOT bundled, so importing it on a
                bare interpreter fails with `ModuleNotFoundError: No module named
                'pyte'`. Installing the package is the supported fix; it also gives
                you the `smartcli-tui` / `smartcli-mcp` console scripts and, on
                Windows, ConPTY support via pywinpty.

                (pyte is deliberately not vendored: this project detects pyte's
                capabilities at import time rather than pinning it, so freezing a
                copy here would work against that.)

VERIFY IT LANDED
    ls ~/.claude/skills/          # cmd-art  drive-tui  tui-ui
    cd ~/.claude/skills/cmd-art && python3 -m fx list      # should print 30 effects

SOURCE / ISSUES
    https://github.com/dwgx/SmartCLI     (MIT)
    Docs: https://smartcli.readthedocs.io/
"""

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src, arc in files:
            z.write(src, arc)
        z.writestr("README.txt", readme)

    print(f"built {target.relative_to(Path.cwd()) if target.is_relative_to(Path.cwd()) else target}")
    print(f"  version : {ver}")
    print(f"  files   : {len(files)} (+ README.txt)")
    print(f"  size    : {target.stat().st_size / 1024:.0f} KiB")
    return target


def verify(zip_path: Path) -> int:
    """Assert the archive is actually installable, not merely non-empty."""
    failures: list[str] = []

    def check(cond: bool, label: str, detail: str = "") -> None:
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail and not cond else ""))
        if not cond:
            failures.append(label)

    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        bad = z.testzip()
        check(bad is None, "archive is not corrupt", detail=f"first bad member: {bad}")

        for skill in SKILLS:
            check(f"{skill}/SKILL.md" in names,
                  f"{skill}/SKILL.md is present (Claude Code needs it to discover the skill)")

        # NOTE the wording: the vendored core removes the need to install
        # smartcli_core, NOT the need for pyte (its third-party dependency,
        # deliberately not vendored). Measured on a bare venv: drive-tui dies
        # with ModuleNotFoundError: pyte. The README says so.
        check(any(n.startswith("drive-tui/_vendor/smartcli_core/") for n in names),
              "drive-tui ships its vendored core (so smartcli_core need not be installed)")

        junk = [n for n in names
                if "__pycache__" in n or n.endswith((".pyc", ".pyo")) or n.endswith(".DS_Store")]
        check(not junk, "no build artifacts or OS noise", detail=f"{len(junk)} found, e.g. {junk[:2]}")

        check("README.txt" in names, "README.txt tells the user where to unzip")
        if "README.txt" in names:
            rd = z.read("README.txt").decode("utf-8", errors="replace")
            # The bundle's whole value is that the install instructions are true. An
            # earlier draft of this README claimed drive-tui "runs as-is" with no pip
            # — measured false on a bare venv. Lock the correction so it cannot
            # silently regress into an overclaim again.
            check("pip install smartcli-toolkit" in rd,
                  "README states drive-tui's pyte requirement")
            check("~/.claude/skills/" in rd,
                  "README gives the actual install path")

        # Every archive path must start with one of the three skill names (or be the
        # README), or unzipping into ~/.claude/skills/ would scatter files.
        stray = [n for n in names
                 if n != "README.txt" and not any(n.startswith(s + "/") for s in SKILLS)]
        check(not stray, "every path is under a skill directory", detail=f"stray: {stray[:3]}")

        ver = version()
        for skill in SKILLS:
            text = z.read(f"{skill}/SKILL.md").decode("utf-8", errors="replace")
            m = re.search(r"^version:\s*(\S+)", text, re.M)
            check(bool(m) and m.group(1) == ver,
                  f"{skill}/SKILL.md declares version {ver}",
                  detail=f"declares {m.group(1) if m else 'nothing'}")

    print()
    if failures:
        print(f"VERIFY FAIL — {len(failures)} check(s):")
        for f in failures:
            print("   -", f)
        return 1
    print(f"VERIFY PASS — {zip_path.name} is a drop-in install for ~/.claude/skills/")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"), help="output directory (default: dist/)")
    ap.add_argument("--verify-only", metavar="ZIP", default=None,
                    help="verify an existing zip instead of building")
    args = ap.parse_args()

    if args.verify_only:
        return verify(Path(args.verify_only))

    if shutil.which("zip") is None:
        pass  # we use zipfile, not the CLI — noted so nobody adds a dependency here
    target = build(Path(args.out))
    print()
    return verify(target)


if __name__ == "__main__":
    sys.exit(main())
