#!/usr/bin/env python
"""test_vendor_sync.py — regression lock: the vendored smartcli_core copy in
drive-tui must stay byte-identical to the canonical top-level smartcli_core.

drive-tui bundles smartcli_core at skills/drive-tui/_vendor/ so the skill folder
is self-contained (drop-in). That copy is a liability if it silently drifts from
the real one — a fix could land in canonical and never reach the vendored path.
This test fails loudly on any drift; refresh with `python tools/sync_vendor.py`.

Pure filesystem comparison — no processes, no PTY. Exit 0 = in sync.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tools"))

import sync_vendor  # noqa: E402


def main() -> int:
    only_can, only_ven, differ = sync_vendor.diff()
    print("=" * 60)
    print("vendored smartcli_core sync lock")
    print("=" * 60)
    if not (only_can or only_ven or differ):
        n = len(sync_vendor._rel_files(sync_vendor.CANONICAL))
        print(f"[PASS] vendored copy byte-identical to canonical ({n} files)")
        return 0
    for rel in sorted(only_can):
        print(f"[FAIL] missing in vendor: {rel}")
    for rel in sorted(only_ven):
        print(f"[FAIL] stale extra in vendor: {rel}")
    for rel in sorted(differ):
        print(f"[FAIL] content differs: {rel}")
    print("Fix: python tools/sync_vendor.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
