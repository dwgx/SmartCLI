#!/usr/bin/env python3
"""test_char_width.py — width function: default stability + the new knobs.

Character cell width is a coordination problem (terminals ship different Unicode
DBs). ui.core.width/char_width gained two optional knobs — unicode_version and
ambiguous_wide — so a caller can pin the answer to its terminal. This locks:
  * defaults are byte-identical to the old behavior (so golden/fx baselines
    don't move),
  * ambiguous_wide flips East-Asian Ambiguous glyphs 1<->2 without touching
    unambiguous ones,
  * CJK / emoji / ZWJ / combining widths are unaffected by the knob,
  * pinning unicode_version doesn't crash.

Pure/in-memory: imports the ui package, computes widths. No process, no PTY.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "tui-ui"))

from ui.core import char_width, width  # noqa: E402

failures = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    global failures
    if not cond:
        failures += 1
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  -- {detail}" if detail else ""))


# East-Asian Ambiguous sample chars (unicodedata.east_asian_width == 'A').
AMBIGUOUS = ["§", "±", "…", "○", "×"]
# Unambiguous references that must never change with the knob.
CJK = "你好"          # each 2 cells
ASCII = "hello"       # each 1 cell
EMOJI = "😀"          # 2 cells
ZWJ = "‍"        # 0 cells


def test_defaults_unchanged() -> None:
    # Default: ambiguous is narrow (1), matching the pre-change behavior.
    for c in AMBIGUOUS:
        check(char_width(c) == 1, f"default: ambiguous U+{ord(c):04X} is 1 cell",
              detail=str(char_width(c)))
    check(width(ASCII) == 5, "default: 'hello' is 5", detail=str(width(ASCII)))
    check(width(CJK) == 4, "default: 2 CJK chars are 4", detail=str(width(CJK)))
    check(char_width(EMOJI) == 2, "default: emoji is 2")
    check(char_width(ZWJ) == 0, "default: ZWJ is 0")


def test_ambiguous_wide_knob() -> None:
    # With the CJK-locale knob, ambiguous glyphs count as 2.
    for c in AMBIGUOUS:
        check(char_width(c, ambiguous_wide=True) == 2,
              f"ambiguous_wide: U+{ord(c):04X} is 2 cells",
              detail=str(char_width(c, ambiguous_wide=True)))
    # A whole string of ambiguous chars scales.
    s = "".join(AMBIGUOUS)
    check(width(s, ambiguous_wide=True) == 2 * len(AMBIGUOUS),
          "ambiguous_wide: string doubles", detail=str(width(s, ambiguous_wide=True)))


def test_knob_leaves_unambiguous_alone() -> None:
    # The knob must ONLY affect ambiguous chars — CJK/ASCII/emoji/ZWJ unchanged.
    check(width(ASCII, ambiguous_wide=True) == 5, "knob: ASCII still 5")
    check(width(CJK, ambiguous_wide=True) == 4, "knob: CJK still 4")
    check(char_width(EMOJI, ambiguous_wide=True) == 2, "knob: emoji still 2")
    check(char_width(ZWJ, ambiguous_wide=True) == 0, "knob: ZWJ still 0")


def test_unicode_version_pin() -> None:
    # Pinning a version must not crash and must return a sane width for ASCII.
    try:
        w = width("hello", unicode_version="9.0.0")
        check(w == 5, "unicode_version='9.0.0' gives 'hello'==5", detail=str(w))
    except Exception as exc:
        check(False, "unicode_version pin did not crash", detail=repr(exc))


def main() -> int:
    test_defaults_unchanged()
    test_ambiguous_wide_knob()
    test_knob_leaves_unambiguous_alone()
    test_unicode_version_pin()
    print()
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
