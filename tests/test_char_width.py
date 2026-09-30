#!/usr/bin/env python3
"""test_char_width.py — width function: default stability + the width knobs.

Character cell width is a coordination problem (terminals ship different Unicode
DBs). ui.core.width/char_width gained optional knobs — unicode_version,
ambiguous_wide, and term_program — so a caller can pin the answer to its
terminal. This locks:
  * defaults are byte-identical to the old behavior (so golden/fx baselines
    don't move),
  * ambiguous_wide flips East-Asian Ambiguous glyphs 1<->2 without touching
    unambiguous ones,
  * CJK / emoji / ZWJ / combining widths are unaffected by that knob,
  * pinning unicode_version doesn't crash,
  * term_program routes through wcwidth's per-terminal correction tables and
    changes VS16 / ZWJ-sequence / flag-pair widths, per terminal,
  * an unknown terminal name degrades to the default instead of raising,
  * a wcwidth too old to know `term_program` degrades to the default instead of
    raising (our declared floor is 0.2.0; the feature postdates it).

Pure/in-memory: imports the ui package, computes widths. No process, no PTY.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "tui-ui"))

from ui import core  # noqa: E402
from ui.core import char_width, width  # noqa: E402

failures = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    global failures
    if not cond:
        failures += 1
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  -- {detail}" if detail else ""))


def knob_missing(label: str) -> None:
    """Report the knob's absence as a normal FAIL, not a mid-run traceback."""
    check(False, f"{label}: width() has no term_program parameter",
          "expected width(s, term_program=...)")


# The knob must be *visible in the signature*, not merely tolerated — a caller
# discovers it by reading `width(...)`. Probed so a core.py without it produces
# a readable FAIL instead of a traceback half way down the run.
KNOB_PRESENT = "term_program" in inspect.signature(width).parameters


def supported() -> bool:
    """Capability read defensively: a core.py without the knob has no attribute."""
    return bool(getattr(core, "TERM_PROGRAM_SUPPORTED", False))


def programs() -> frozenset:
    return getattr(core, "TERM_PROGRAMS", frozenset())


# East-Asian Ambiguous sample chars (unicodedata.east_asian_width == 'A').
AMBIGUOUS = ["§", "±", "…", "○", "×"]
# Unambiguous references that must never change with the ambiguous knob.
CJK = "你好"          # each 2 cells
ASCII = "hello"       # each 1 cell
EMOJI = "\U0001f600"  # 2 cells
ZWJ = "‍"        # 0 cells
RI = "\U0001f1e8"     # lone regional indicator

# --- term_program cases: the three constructs whose width a terminal decides ---
VS16 = "❤️"                    # U+2764 U+FE0F — text vs emoji presentation
ZWJ_SEQ = "\U0001f469‍\U0001f4bb"  # woman + ZWJ + laptop
FLAG = "\U0001f1e8\U0001f1f3"       # regional indicators C + N

# ucs-detect scores Windows Terminal / kitty / ghostty / mintty / wezterm at 100
# for ZWJ and VS16 — they CLUSTER — while xterm/st/urxvt/alacritty score 1. These
# two disagree about all three constructs, so pinning both proves the knob reads
# a per-terminal table rather than returning a constant.
CLUSTERING = "kitty"
NON_CLUSTERING = "xterm"


def test_defaults_unchanged() -> None:
    # Default: ambiguous is narrow (1), matching the pre-change behavior.
    for c in AMBIGUOUS:
        check(char_width(c) == 1, f"default: ambiguous U+{ord(c):04X} is 1 cell",
              detail=str(char_width(c)))
    check(width(ASCII) == 5, "default: 'hello' is 5", detail=str(width(ASCII)))
    check(width(CJK) == 4, "default: 2 CJK chars are 4", detail=str(width(CJK)))
    check(char_width(EMOJI) == 2, "default: emoji is 2")
    check(char_width(ZWJ) == 0, "default: ZWJ is 0")


def test_default_is_explicitly_none() -> None:
    # The knob's default must be *absence*, not a value: passing term_program=None
    # explicitly has to take the identical path, or a caller forwarding an unset
    # config would get different arithmetic than one not forwarding at all.
    if not KNOB_PRESENT:
        knob_missing("term_program=None default")
        return
    for s in (ASCII, CJK, EMOJI, VS16, ZWJ_SEQ, FLAG, "".join(AMBIGUOUS)):
        check(width(s, term_program=None) == width(s),
              f"term_program=None is identical to the default for {s!r}",
              detail=f"{width(s)} vs {width(s, term_program=None)}")
    for c in (AMBIGUOUS[0], EMOJI, ZWJ, RI):
        check(char_width(c, term_program=None) == char_width(c),
              f"char_width term_program=None is identical for U+{ord(c):04X}",
              detail=f"{char_width(c)} vs {char_width(c, term_program=None)}")


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


def test_term_program_capability_is_reported() -> None:
    # The module must say out loud whether the installed wcwidth can do this, so
    # a caller never has to sniff it — and a 0.2.x install is distinguishable
    # from a terminal that merely measures the same as our default.
    check(isinstance(getattr(core, "TERM_PROGRAM_SUPPORTED", None), bool),
          "core.TERM_PROGRAM_SUPPORTED is a bool",
          detail=repr(getattr(core, "TERM_PROGRAM_SUPPORTED", None)))
    check(isinstance(getattr(core, "TERM_PROGRAMS", None), frozenset),
          "core.TERM_PROGRAMS is a frozenset")
    if not KNOB_PRESENT:
        knob_missing("capability report")
        return
    if supported():
        # This box has 0.8.2 / 33 terminals. Assert the knob is actually live
        # rather than silently degrading: a green run here must mean "the tables
        # were consulted", not "we fell back and nobody noticed".
        check(len(programs()) >= 20,
              "supported wcwidth exposes a real terminal-name table",
              detail=f"{len(programs())} names")
        for name in (CLUSTERING, NON_CLUSTERING):
            check(name in programs(), f"'{name}' is in the terminal-name table")


def test_term_program_changes_vs16_zwj_flag() -> None:
    """VS16 / ZWJ sequence / flag pair must actually move, per terminal."""
    if not KNOB_PRESENT:
        knob_missing("term_program opt-in path")
        return
    if not supported():
        check(False, "term_program knob is live on this wcwidth",
              "installed wcwidth predates the per-terminal tables; the opt-in "
              "path cannot be asserted here")
        return
    # BEFORE (our default, per-codepoint): VS16 base+selector = 1+0, ZWJ family
    # = 2+0+2, flag pair = 2+2.
    check(width(VS16) == 1, "default: VS16 pair is 1 cell", detail=str(width(VS16)))
    check(width(ZWJ_SEQ) == 4, "default: ZWJ sequence is 4 cells",
          detail=str(width(ZWJ_SEQ)))
    check(width(FLAG) == 4, "default: flag pair is 4 cells", detail=str(width(FLAG)))
    # AFTER (a clustering terminal): the sequence collapses to one cluster.
    check(width(VS16, term_program=CLUSTERING) == 2,
          f"{CLUSTERING}: VS16 pair is 2 cells",
          detail=str(width(VS16, term_program=CLUSTERING)))
    check(width(ZWJ_SEQ, term_program=CLUSTERING) == 2,
          f"{CLUSTERING}: ZWJ sequence is 2 cells",
          detail=str(width(ZWJ_SEQ, term_program=CLUSTERING)))
    check(width(FLAG, term_program=CLUSTERING) == 2,
          f"{CLUSTERING}: flag pair is 2 cells",
          detail=str(width(FLAG, term_program=CLUSTERING)))
    # AFTER (a non-clustering terminal): must DIFFER from the clustering answer,
    # else the knob would be measuring a constant rather than a table.
    check(width(VS16, term_program=NON_CLUSTERING) == 1,
          f"{NON_CLUSTERING}: VS16 pair is 1 cell",
          detail=str(width(VS16, term_program=NON_CLUSTERING)))
    check(width(ZWJ_SEQ, term_program=NON_CLUSTERING) == 4,
          f"{NON_CLUSTERING}: ZWJ sequence is 4 cells",
          detail=str(width(ZWJ_SEQ, term_program=NON_CLUSTERING)))
    check(width(FLAG, term_program=NON_CLUSTERING) == 1,
          f"{NON_CLUSTERING}: flag pair is 1 cell",
          detail=str(width(FLAG, term_program=NON_CLUSTERING)))
    # Print the real numbers so the change is visible, not merely asserted.
    print("      before/after (kitty)  VS16 %d->%d  ZWJseq %d->%d  FLAG %d->%d" % (
        width(VS16), width(VS16, term_program=CLUSTERING),
        width(ZWJ_SEQ), width(ZWJ_SEQ, term_program=CLUSTERING),
        width(FLAG), width(FLAG, term_program=CLUSTERING)))
    print("      before/after (xterm)  VS16 %d->%d  ZWJseq %d->%d  FLAG %d->%d" % (
        width(VS16), width(VS16, term_program=NON_CLUSTERING),
        width(ZWJ_SEQ), width(ZWJ_SEQ, term_program=NON_CLUSTERING),
        width(FLAG), width(FLAG, term_program=NON_CLUSTERING)))


def test_term_program_leaves_plain_text_alone() -> None:
    # ASCII/CJK are what the engine lays out; the knob must not move them on any
    # terminal, or every box border would shift next to emoji-adjacent content.
    if not KNOB_PRESENT or not supported():
        return
    for name in sorted(programs()):
        check(width(ASCII, term_program=name) == 5,
              f"{name}: ASCII still 5", detail=str(width(ASCII, term_program=name)))
        check(width(CJK, term_program=name) == 4,
              f"{name}: CJK still 4", detail=str(width(CJK, term_program=name)))


def test_term_program_strips_ansi_first() -> None:
    # The opt-in path must measure what is displayed, exactly as the default does.
    if not KNOB_PRESENT or not supported():
        return
    s = "\x1b[31m" + FLAG + "\x1b[0m"
    got = width(s, term_program=CLUSTERING)
    want = width(FLAG, term_program=CLUSTERING)
    check(got == want, "term_program path strips ANSI before measuring",
          detail=f"{got} vs {want}")


def test_char_width_term_program_scalar() -> None:
    # A lone regional indicator: 2 cells per-codepoint, 1 on terminals that pair
    # them. This is the char_width-level half of the knob.
    check(char_width(RI) == 2, "default: lone regional indicator is 2 cells",
          detail=str(char_width(RI)))
    if not KNOB_PRESENT or not supported():
        return
    check(char_width(RI, term_program=NON_CLUSTERING) == 1,
          f"{NON_CLUSTERING}: lone regional indicator is 1 cell",
          detail=str(char_width(RI, term_program=NON_CLUSTERING)))
    check(char_width(RI, term_program=CLUSTERING) == 2,
          f"{CLUSTERING}: lone regional indicator stays 2 cells",
          detail=str(char_width(RI, term_program=CLUSTERING)))


def test_unknown_terminal_degrades() -> None:
    # A typo must not raise, and must not silently produce a THIRD answer: it has
    # to land on today's default, exactly.
    if not KNOB_PRESENT:
        knob_missing("unknown-terminal degradation")
        return
    for bad in ("NoSuchTerminal", "", "kitty ", "KITTY", "xterm-256color"):
        for s in (ASCII, CJK, VS16, ZWJ_SEQ, FLAG):
            try:
                got = width(s, term_program=bad)
            except Exception as exc:
                check(False, f"unknown terminal {bad!r} did not raise", detail=repr(exc))
                continue
            check(got == width(s), f"unknown terminal {bad!r} degrades to default",
                  detail=f"{got} vs {width(s)}")
        try:
            got = char_width(RI, term_program=bad)
            check(got == 2, f"char_width unknown terminal {bad!r} degrades to default",
                  detail=str(got))
        except Exception as exc:
            check(False, f"char_width unknown terminal {bad!r} did not raise",
                  detail=repr(exc))


def test_old_wcwidth_degrades() -> None:
    """A wcwidth without `term_program` must fall back, not raise.

    Our declared floor is wcwidth>=0.2.0, six minor versions before the keyword
    existed, so this is the *normal* case on a floor install. Simulated two ways:
    the version probe reporting False, and a string function that blows up with
    the TypeError a real old wcwidth raises.
    """
    if not KNOB_PRESENT:
        knob_missing("old-wcwidth degradation")
        return
    samples = (ASCII, CJK, VS16, ZWJ_SEQ, FLAG)
    saved_supported = core.TERM_PROGRAM_SUPPORTED
    saved_programs = core.TERM_PROGRAMS
    saved_pkg = core._wcstwidth_pkg
    try:
        core.TERM_PROGRAM_SUPPORTED = False
        core.TERM_PROGRAMS = frozenset()
        for s in samples:
            try:
                got = width(s, term_program="kitty")
                check(got == width(s), "probe-off (0.2.x shape) degrades to default",
                      detail=f"{got} vs {width(s)}")
            except Exception as exc:
                check(False, "probe-off (0.2.x shape) did not raise", detail=repr(exc))

        # A build that HAS the string function but not the keyword — the case the
        # one-shot import-time probe cannot pre-empt on its own.
        def old_wcstwidth(s, n=None, unicode_version="auto", ambiguous_width=1):
            return len(s) if n is None else 0

        core.TERM_PROGRAM_SUPPORTED = True
        core.TERM_PROGRAMS = frozenset({"kitty"})
        core._wcstwidth_pkg = old_wcstwidth
        for s in samples:
            try:
                got = width(s, term_program="kitty")
                check(got == width(s),
                      "keyword-less string function degrades to default",
                      detail=f"{got} vs {width(s)}")
            except Exception as exc:
                check(False, "keyword-less string function did not raise",
                      detail=repr(exc))
    finally:
        core.TERM_PROGRAM_SUPPORTED = saved_supported
        core.TERM_PROGRAMS = saved_programs
        core._wcstwidth_pkg = saved_pkg
    # The monkeypatching must not leak into the rest of the suite.
    check(supported() == saved_supported and programs() == saved_programs,
          "old-wcwidth simulation restores module state")


def main() -> int:
    test_defaults_unchanged()
    test_default_is_explicitly_none()
    test_ambiguous_wide_knob()
    test_knob_leaves_unambiguous_alone()
    test_unicode_version_pin()
    test_term_program_capability_is_reported()
    test_term_program_changes_vs16_zwj_flag()
    test_term_program_leaves_plain_text_alone()
    test_term_program_strips_ansi_first()
    test_char_width_term_program_scalar()
    test_unknown_terminal_degrades()
    test_old_wcwidth_degrades()
    print()
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
