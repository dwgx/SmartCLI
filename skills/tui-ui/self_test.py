"""self_test.py — bounded self-test for the tui-ui engine (no infinite loop).

Renders the composed dashboard ONCE at each of several sizes and asserts the
render is sound:
  1. exactly H rows, each exactly W display cells wide (no fr drift) — checked
     at 100x30, 40x12, 80x24, 120x40, and 200x50;
  2. box-drawing glyphs present (real borders, not ASCII fallback);
  3. truecolor SGR present in the ANSI output;
  4. the CJK row (``cache-西``) keeps its table columns aligned — the vertical
     bars sit at the SAME columns as a pure-ASCII row, proving wide-char aware
     width. Also checks the width() edge cases from the research digest.

Run:  python self_test.py        (from skills/tui-ui)
Exit code 0 = pass, 1 = fail. Prints a short evidence report.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import core, get_theme
from ui.cli import _build_gallery


def _bar_columns(line: str) -> list[int]:
    """Column indices (in display cells) of vertical box bars in a line."""
    cols = []
    col = 0
    for ch in line:
        if ch in ("│", "┃", "║"):
            cols.append(col)
        col += core.char_width(ch)
    return cols


def main() -> int:
    fails = []

    # --- width() edge cases -----------------------------------------------
    # CONTRACT: width() is the PER-CODEPOINT cell sum, identical to what a VT
    # terminal (pyte/tmux) advances the cursor by and to what Canvas.put_text
    # draws. It is NOT grapheme-cluster width. That identity is what keeps table
    # columns aligned with the rendered grid: a ZWJ emoji or a regional-indicator
    # flag consumes the sum of its scalar widths (flag pair = 2+2 = 4), because
    # that is exactly how the terminal lays them out. Verified against pyte.
    cases = [("é", 1), ("界", 2), ("♀️", 1), ("👩‍💻", 4),
             ("🇯🇵", 4), ("\x1b[31mred", 3), ("你好", 4), ("😀", 2)]
    for s, exp in cases:
        got = core.width(s)
        if got != exp:
            fails.append(f"width({s!r})={got}, expected {exp}")

    # --- render the dashboard at several sizes ----------------------------
    # SIZES: the primary 100x30 plus a spread of aspect ratios/scales. Every
    # one must produce exactly H rows of exactly W display cells (no fr drift).
    SIZES = [(100, 30), (40, 12), (80, 24), (120, 40), (200, 50)]
    # keep the primary size's artifacts for the box/truecolor/CJK checks below
    lines = ansi = all_text = None
    size_report = []
    for W, H in SIZES:
        page = _build_gallery(get_theme("dashboard"), W, H)
        s_ansi = page.to_ansi()
        s_lines = page.to_lines()

        # 1. shape + width at this size
        row_ok = len(s_lines) == H
        if not row_ok:
            fails.append(f"[{W}x{H}] row count {len(s_lines)} != {H}")
        off = [(i, core.width(l)) for i, l in enumerate(s_lines) if core.width(l) != W]
        if off:
            fails.append(f"[{W}x{H}] {len(off)} rows not {W} cells wide: {off[:5]}")
        size_report.append((W, H, len(s_lines), row_ok and not off))

        if (W, H) == (100, 30):
            lines, ansi, all_text = s_lines, s_ansi, "\n".join(s_lines)

    # 2. box drawing present (primary size)
    if not any(g in all_text for g in "─│┌┐└┘├┤┬┴┼╭╮╰╯"):
        fails.append("no box-drawing glyphs found")

    # 3. truecolor SGR present
    if "\x1b[38;2;" not in ansi:
        fails.append("no truecolor (38;2) SGR in ANSI output")

    # 4. CJK column alignment: render a standalone table whose rows have IDENTICAL
    #    structure but different char widths, then assert the vertical bars land
    #    on exactly the same columns (proves wide-char aware width, not len()).
    from ui.widgets import Table
    from ui import Page
    tbl = Table(headers=["Node", "State"],
                rows=[["ascii-node", "up"], ["cjk-你好界", "up"]],
                theme=get_theme("dashboard"))
    tlines = Page(tbl, width=40, height=6).to_lines()
    ascii_row = next((l for l in tlines if "ascii-node" in l), None)
    cjk_row = next((l for l in tlines if "你好界" in l), None)
    if ascii_row is None or cjk_row is None:
        fails.append("could not find CJK / ASCII table rows")
    else:
        cjk_bars = _bar_columns(cjk_row)
        ascii_bars = _bar_columns(ascii_row)
        if cjk_bars != ascii_bars:
            fails.append(f"CJK row misaligned: bars {cjk_bars} != {ascii_bars}")

    # --- report -----------------------------------------------------------
    print("=" * 60)
    print("tui-ui self-test  (pyte-independent; pure render assertions)")
    print("=" * 60)
    for W, H, nrows, ok in size_report:
        print(f"render {W:>3}x{H:<2} : {nrows} rows, all {W} cells wide: "
              f"{'YES' if ok else 'NO'}")
    has_box = any(g in all_text for g in "─│┌┐└┘")
    has_tc = "\x1b[38;2;" in ansi
    print(f"box-drawing    : {'YES' if has_box else 'NO'}")
    print(f"truecolor SGR  : {'YES' if has_tc else 'NO'}")
    if ascii_row and cjk_row:
        print(f"ASCII row      : |{ascii_row}|")
        print(f"CJK row        : |{cjk_row}|")
        print(f"CJK bar cols   : {_bar_columns(cjk_row)}")
        print(f"ASCII bar cols : {_bar_columns(ascii_row)}")
        print(f"columns match  : {'YES' if _bar_columns(cjk_row) == _bar_columns(ascii_row) else 'NO'}")
    print(f"width() cases  : {'all OK' if not any('width(' in f for f in fails) else 'FAIL'}")
    print("-" * 60)
    if fails:
        print("FAIL:")
        for f in fails:
            print("  -", f)
        return 1
    print("PASS: aligned box-drawing + truecolor, no CJK misalignment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
