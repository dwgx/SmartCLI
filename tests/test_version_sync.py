#!/usr/bin/env python3
"""test_version_sync.py — anti-drift gate: the TEN version sites must agree.

A version bump must move ten sites together (see CLAUDE.md "Version bump = TEN
sites"). plugin.json is the site that historically drifted (it sat at 0.1.2
while everything else was 0.1.8) — exactly what this catches. Pure/in-memory:
reads files with regex/json, never imports the packages, never spawns a
process. Fails (exit 1) if any site disagrees with pyproject.toml.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FAILURES = []


def check(cond, label):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        FAILURES.append(label)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def regex_one(rel: str, pattern: str) -> str:
    m = re.search(pattern, read(rel), re.MULTILINE)
    if not m:
        raise AssertionError(f"{rel}: pattern {pattern!r} not found")
    return m.group(1)


# The reference value every other site must match.
REFERENCE = regex_one("pyproject.toml", r'^version\s*=\s*"([^"]+)"')
print(f"reference version (pyproject.toml): {REFERENCE}")

marketplace = json.loads(read(".claude-plugin/marketplace.json"))
plugin = json.loads(read(".claude-plugin/plugin.json"))
server = json.loads(read("server.json"))

SITES = {
    "smartcli_core/__init__.py __version__": regex_one(
        "smartcli_core/__init__.py", r'^__version__\s*=\s*"([^"]+)"'),
    "vendored _vendor/smartcli_core/__init__.py __version__": regex_one(
        "skills/drive-tui/_vendor/smartcli_core/__init__.py",
        r'^__version__\s*=\s*"([^"]+)"'),
    "skills/cmd-art/fx/__init__.py __version__": regex_one(
        "skills/cmd-art/fx/__init__.py", r'^__version__\s*=\s*"([^"]+)"'),
    "skills/drive-tui/SKILL.md version:": regex_one(
        "skills/drive-tui/SKILL.md", r"^version:\s*(\S+)"),
    "skills/cmd-art/SKILL.md version:": regex_one(
        "skills/cmd-art/SKILL.md", r"^version:\s*(\S+)"),
    "skills/tui-ui/SKILL.md version:": regex_one(
        "skills/tui-ui/SKILL.md", r"^version:\s*(\S+)"),
    ".claude-plugin/marketplace.json plugins[0].version":
        marketplace["plugins"][0]["version"],
    ".claude-plugin/plugin.json version": plugin["version"],
    "server.json version (top-level)": server["version"],
    "server.json packages[0].version": server["packages"][0]["version"],
}

for label, value in SITES.items():
    check(value == REFERENCE, f"{label} == {REFERENCE}"
          + ("" if value == REFERENCE else f" -> got {value}"))

if FAILURES:
    print(f"\ntest_version_sync FAIL -- {len(FAILURES)} site(s) drifted "
          f"from pyproject.toml {REFERENCE}:")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print(f"\nPASS: all ten version sites agree ({REFERENCE})")
sys.exit(0)
