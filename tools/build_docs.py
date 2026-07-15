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


import re

GH_BLOB = "https://github.com/dwgx/SmartCLI/blob/main/"
# A markdown link whose target is a repo-relative path (not http(s):, not a #
# anchor, not a mailto). These are correct on GitHub but dangling on the docs
# site — especially the localized READMEs (docs/i18n/*.md), which are excluded
# from the site by mkdocs.yml, so the language switcher would 404. Rewrite them
# to absolute GitHub URLs so every such link resolves from the site too.
_LINK_RE = re.compile(r"(\]\()(?!https?://|#|mailto:)([^)]+)(\))")


def _rewrite_repo_links(text: str, src_rel: str) -> str:
    src_dir = "/".join(src_rel.split("/")[:-1])  # dir of the source doc in the repo

    def repl(m: re.Match) -> str:
        target = m.group(2)
        anchor = ""
        if "#" in target:
            target, anchor = target.split("#", 1)
            anchor = "#" + anchor
        if not target:  # pure in-page anchor like (#section)
            return m.group(0)
        # Resolve the link relative to the SOURCE doc's directory, then normalize
        # ../ segments, so e.g. README-USAGE's "skills/x" and an i18n file's
        # "../../LICENSE" both land on the right repo path.
        base = src_dir
        parts = (base.split("/") if base else []) + target.split("/")
        stack: list[str] = []
        for p in parts:
            if p in ("", "."):
                continue
            if p == "..":
                if stack:
                    stack.pop()
            else:
                stack.append(p)
        return f"{m.group(1)}{GH_BLOB}{'/'.join(stack)}{anchor}{m.group(3)}"

    return _LINK_RE.sub(repl, text)


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    missing = []
    for src_rel, dst_name in MAPPING:
        src = ROOT / src_rel
        if not src.exists():
            missing.append(src_rel)
            continue
        text = src.read_text(encoding="utf-8")
        text = _rewrite_repo_links(text, src_rel)
        (DOCS / dst_name).write_text(text, encoding="utf-8")
        print(f"  {src_rel} -> docs/{dst_name}")
    if missing:
        print(f"error: missing source docs: {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"assembled {len(MAPPING)} docs into {DOCS}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
