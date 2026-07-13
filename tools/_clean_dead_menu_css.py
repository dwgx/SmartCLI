#!/usr/bin/env python3
"""_clean_dead_menu_css.py — remove the dead legacy .menu/.mrow/.mtitle CSS block
(and the --fg/--grn aliases that only served it) from the localized pages, now
that the DRIVE-TUI toy uses the live .cc-menu. Idempotent. Not shipped."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs" / "site"
PAGES = ["index.zh-Hans.html", "index.zh-Hant.html", "index.ja.html", "index.ko.html"]

DEAD_CSS = """  /* drive-tui menu toy — fills the fixed stage */
  .menu{font-family:var(--mono);font-size:14px;padding:14px 16px;outline:none;
    cursor:pointer;height:100%}
  .menu:focus{box-shadow:inset 0 0 0 2px var(--coral)}
  .mtitle{color:var(--on-dark-soft);font-size:12px;margin-bottom:10px}
  .mrow{color:var(--on-dark-soft);padding:3px 0;transition:color .18s ease}
  .mrow .arrow{opacity:0;color:var(--teal);margin-right:8px;
    transition:opacity .18s ease}
  .mrow.sel{color:var(--fg)}
  .mrow.sel .arrow{opacity:1}
  .mrow.done{color:var(--grn)}
"""

FG_LINE = "\n    --fg:#faf9f5; --grn:#5db872;  /* aliases for the legacy DRIVE-TUI menu rows */"


def main() -> int:
    for name in PAGES:
        p = SITE / name
        if not p.exists():
            print(f"SKIP {name}: missing"); continue
        s = p.read_text(encoding="utf-8")
        changed = []
        if DEAD_CSS in s:
            s = s.replace(DEAD_CSS, "", 1); changed.append("dead menu CSS")
        if FG_LINE in s:
            s = s.replace(FG_LINE, "", 1); changed.append("--fg/--grn aliases")
        if changed:
            p.write_text(s, encoding="utf-8")
            print(f"OK {name}: removed {', '.join(changed)}")
        else:
            print(f"SKIP {name}: nothing to remove (already clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
