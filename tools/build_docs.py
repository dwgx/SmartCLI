#!/usr/bin/env python3
"""build_docs.py — assemble the mkdocs `docs/` tree from the canonical sources.

mkdocs.yml's nav points at docs/*.md stubs that are NOT hand-authored and NOT
committed: they are copies of the real docs (README, README-USAGE, the three
SKILL.md files, knowledge/INDEX.md, CHANGELOG.md). Generating them at build time
means the site can never drift from the source of truth — there is exactly one
copy of each doc in the repo, and the site mirrors it.

Read the Docs runs this via .readthedocs.yaml before `mkdocs build`. Locally:

    python tools/build_docs.py           # generate docs/*.md
    python -m mkdocs build --strict      # then build (fails on broken links)
    python -m mkdocs serve               # or preview

The generated files are gitignored (see .gitignore). Run this before any local
mkdocs command.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# (source relative to repo root, destination filename under docs/). These match
# the nav in mkdocs.yml exactly — keep them in sync if you change the nav.
MAPPING = [
    ("README.md", "index.md"),
    ("README-USAGE.md", "usage.md"),
    ("skills/cmd-art/SKILL.md", "skills-cmd-art.md"),
    ("skills/drive-tui/SKILL.md", "skills-drive-tui.md"),
    ("skills/tui-ui/SKILL.md", "skills-tui-ui.md"),
    ("knowledge/INDEX.md", "knowledge.md"),
    ("CHANGELOG.md", "changelog.md"),
]


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    missing = []
    for src_rel, dst_name in MAPPING:
        src = ROOT / src_rel
        if not src.exists():
            missing.append(src_rel)
            continue
        shutil.copyfile(src, DOCS / dst_name)
        print(f"  {src_rel} -> docs/{dst_name}")
    if missing:
        print(f"error: missing source docs: {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"assembled {len(MAPPING)} docs into {DOCS}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
