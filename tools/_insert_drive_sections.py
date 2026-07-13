#!/usr/bin/env python3
"""_insert_drive_sections.py — insert the translated drive/three-OS sections into
each localized page, right before its fx-captures band-soft section. One-shot,
idempotent (skips if already inserted). Not shipped."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs" / "site"

# page -> (translated-sections file, the eyebrow text that marks the fx section)
PAGES = {
    "index.zh-Hans.html": ("_zh-Hans_drive_sections.html", "真实录制"),
    "index.zh-Hant.html": ("_zh-Hant_drive_sections.html", "真實錄製"),
    "index.ja.html": ("_ja_drive_sections.html", "実際のキャプチャ"),
    "index.ko.html": ("_ko_drive_sections.html", "실제 캡처"),
}

MARKER = "eyebrow\">증명"  # a per-lang sentinel is set below; overridden per page


def main() -> int:
    for page, (frag_name, fx_eyebrow) in PAGES.items():
        p = SITE / page
        frag = SITE / frag_name
        if not p.exists():
            print(f"SKIP {page}: page missing"); continue
        if not frag.exists():
            print(f"WAIT {page}: {frag_name} not written yet"); continue
        html = p.read_text(encoding="utf-8")
        sections = frag.read_text(encoding="utf-8").strip()
        # idempotency: the new content has a unique class .gifs-3
        if "gifs gifs-3" in html:
            print(f"SKIP {page}: already inserted"); continue
        # anchor: the <section ...> line that opens the fx-captures block, found
        # by its eyebrow text. Insert the fragment + a blank line before it.
        anchor = f'<span class="eyebrow">{fx_eyebrow}</span>'
        idx = html.find(anchor)
        if idx == -1:
            print(f"SKIP {page}: fx eyebrow '{fx_eyebrow}' not found"); continue
        # back up to the start of the enclosing <section ...> line
        sec_start = html.rfind("<section", 0, idx)
        if sec_start == -1:
            print(f"SKIP {page}: no <section before fx eyebrow"); continue
        new = html[:sec_start] + sections + "\n\n" + html[sec_start:]
        p.write_text(new, encoding="utf-8")
        print(f"OK {page}: inserted {len(sections)} chars before fx section")
    return 0


if __name__ == "__main__":
    sys.exit(main())
