#!/usr/bin/env python3
"""_port_ccmenu.py — make the DRIVE-TUI arrow-key menu work on the localized
pages by porting the live cc-menu from the English page: (1) inject the cc-*
CSS block, (2) swap the static menu/mrow toy for the empty cc-menu div that
ccmenu.js populates, (3) load ccmenu.js. Idempotent. Not shipped.

The cc-menu content is ccmenu.js-driven and English (it reproduces the real
Claude Code /model menu), so the toy shows the CLI's real UI on every locale —
that's intended (it's showing the actual program, not translated chrome)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs" / "site"
PAGES = ["index.zh-Hans.html", "index.zh-Hant.html", "index.ja.html", "index.ko.html"]

# The self-contained cc-* CSS block copied verbatim from index.html (246-283).
CC_CSS = """  /* drive-tui menu toy — faithful Claude Code slash-command menu (nested).
     Colors are Claude Code's real dark-theme tokens. */
  .cc-menu{--cc-suggestion:rgb(177,185,249);--cc-success:rgb(78,186,101);
    --cc-inactive:rgb(153,153,153);--cc-claude:rgb(215,119,87);
    --cc-warning:rgb(255,193,7);--cc-error:rgb(255,107,128);
    height:100%;padding:12px 14px;outline:none;font-family:var(--mono);
    font-size:13px;line-height:1.55;color:var(--on-dark);cursor:pointer;
    display:flex;flex-direction:column;overflow:hidden}
  .cc-menu:focus{box-shadow:none}
  .cc-title{color:var(--cc-claude);font-weight:600;margin-bottom:2px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cc-sub{color:var(--cc-inactive);font-size:11px;margin-bottom:8px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cc-rows{flex:1 1 auto;overflow:hidden}
  .cc-row{display:flex;align-items:baseline;gap:7px;padding:2px 6px;
    border-radius:5px;white-space:nowrap}
  .cc-mk{flex:0 0 auto;width:1ch;color:transparent}
  .cc-row.sel{background:rgba(255,255,255,.05);
    box-shadow:inset 2px 0 0 var(--cc-suggestion)}
  .cc-row.sel .cc-mk{color:var(--cc-suggestion)}
  .cc-row.sel .cc-cmd{color:var(--cc-claude)}
  .cc-row.sel .cc-label{color:#fff}
  .cc-row.sel .cc-desc{color:#e8e6f6}
  .cc-cmd{flex:0 0 auto;color:var(--cc-claude)}
  .cc-label{flex:0 0 auto;color:var(--on-dark)}
  .cc-desc{flex:1 1 auto;color:var(--cc-inactive);overflow:hidden;
    text-overflow:ellipsis;font-size:12px}
  .cc-tick{flex:0 0 auto;color:var(--cc-success);margin-left:4px}
  .cc-val{flex:0 0 auto;margin-left:auto;padding-left:10px;color:var(--cc-inactive);
    font-variant-numeric:tabular-nums}
  .cc-caret{flex:0 0 auto;color:var(--cc-inactive)}
  .cc-foot{margin-top:8px;padding-top:7px;border-top:1px solid #2a2622;
    color:var(--cc-inactive);font-size:11px;white-space:nowrap;overflow:hidden}
  .cc-result{flex:1 1 auto;white-space:pre-wrap;color:var(--cc-success);
    font-size:12.5px;padding:4px 2px}
  .cc-result .cc-warn{color:var(--cc-warning)}
  .cc-effort{color:var(--cc-inactive);font-size:11px;margin-left:2ch}

"""

NEW_TOY_STAGE = '<div class="toy-stage"><div class="cc-menu" id="drive-menu" tabindex="0"></div></div>'


def main() -> int:
    for name in PAGES:
        p = SITE / name
        if not p.exists():
            print(f"SKIP {name}: missing"); continue
        s = p.read_text(encoding="utf-8")
        if "cc-menu" in s:
            print(f"SKIP {name}: already ported"); continue

        # 1) inject cc-* CSS right before the .widgets{ rule
        anchor = "  .widgets{font-family:var(--mono)"
        if anchor not in s:
            print(f"SKIP {name}: .widgets CSS anchor not found"); continue
        s = s.replace(anchor, CC_CSS + anchor, 1)

        # 2) replace the static menu toy-stage with the empty cc-menu div.
        #    Match from the toy-stage opening to the closing </div></div> that
        #    precedes the drive-log toy-cap.
        pat = re.compile(
            r'<div class="toy-stage"><div class="menu" id="drive-menu"[^>]*>.*?</div></div>',
            re.DOTALL)
        s2, n = pat.subn(NEW_TOY_STAGE, s, count=1)
        if n != 1:
            print(f"SKIP {name}: static menu block not matched (n={n})"); continue
        s = s2

        # 3) load ccmenu.js after toys.js
        js_anchor = '<script src="assets/toys.js"></script>'
        if js_anchor in s and 'ccmenu.js' not in s:
            s = s.replace(js_anchor,
                          js_anchor + '\n<script src="assets/ccmenu.js"></script>', 1)

        p.write_text(s, encoding="utf-8")
        print(f"OK {name}: cc-menu CSS + live menu + ccmenu.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
