#!/usr/bin/env python
"""sync_vendor.py — refresh the vendored copy of smartcli_core inside drive-tui.

drive-tui bundles a copy of ``smartcli_core`` at
``skills/drive-tui/_vendor/smartcli_core`` so the skill folder is self-contained:
someone can drop just that folder into an AI's skills directory and it still
works, with no repo-root assumption. The canonical source stays the top-level
``smartcli_core/``; this script copies it into the vendor location verbatim.

Usage:
    python tools/sync_vendor.py           # refresh the vendored copy
    python tools/sync_vendor.py --check   # exit 1 if the copy is stale (CI/gate)

The paired test ``tests/test_vendor_sync.py`` runs ``--check`` semantics so a
drift between canonical and vendored can never land silently.
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = _ROOT / "smartcli_core"
VENDORED = _ROOT / "skills" / "drive-tui" / "_vendor" / "smartcli_core"
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def _rel_files(base: Path) -> set[str]:
    return {
        str(p.relative_to(base)).replace("\\", "/")
        for p in base.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def diff() -> tuple[set[str], set[str], set[str]]:
    """Return (only_in_canonical, only_in_vendored, differing_content)."""
    can = _rel_files(CANONICAL)
    ven = _rel_files(VENDORED) if VENDORED.exists() else set()
    only_can = can - ven
    only_ven = ven - can
    differ = set()
    for rel in can & ven:
        if not filecmp.cmp(CANONICAL / rel, VENDORED / rel, shallow=False):
            differ.add(rel)
    return only_can, only_ven, differ


def is_synced() -> bool:
    only_can, only_ven, differ = diff()
    return not (only_can or only_ven or differ)


def refresh() -> None:
    if VENDORED.exists():
        shutil.rmtree(VENDORED)
    VENDORED.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CANONICAL, VENDORED, ignore=_IGNORE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the vendored copy is stale (no writes)")
    args = ap.parse_args()

    if args.check:
        only_can, only_ven, differ = diff()
        if only_can or only_ven or differ:
            print("VENDOR OUT OF SYNC with canonical smartcli_core/:")
            for rel in sorted(only_can):
                print(f"  missing in vendor: {rel}")
            for rel in sorted(only_ven):
                print(f"  stale extra in vendor: {rel}")
            for rel in sorted(differ):
                print(f"  content differs: {rel}")
            print("Run: python tools/sync_vendor.py")
            return 1
        print("vendor in sync with canonical smartcli_core/")
        return 0

    refresh()
    print(f"refreshed {VENDORED.relative_to(_ROOT)} from {CANONICAL.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
