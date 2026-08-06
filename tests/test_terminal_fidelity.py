#!/usr/bin/env python3
"""test_terminal_fidelity.py — locks for divergences found against a REAL terminal.

Every check here corresponds to a case where our screen model disagreed with
tmux 3.6b (and, where it mattered, GNU screen as an independent referee). They
are deterministic and tmux-free so they gate in CI on every platform, while
``_diff_tmux_pyte.py`` / ``_diff_fuzz_tmux.py`` keep looking for new ones.

``pyte.Screen.draw`` walks a batch character by character and, on a character
that is neither width-1, width-2, nor a true combining mark, does ``else:
break`` — dropping every remaining character in that batch. VARIATION
SELECTOR-16 (U+FE0F) and ZERO WIDTH JOINER (U+200D) both land in that hole, so a
program that printed an emoji mid-line lost everything after it and the agent
perceived a truncated screen.

Found by ``tests/_diff_tmux_pyte.py`` (real tmux keeps the whole line, we did
not). ``ScreenModel`` now attaches those codepoints to the previous cell, the
way pyte already handles combining marks. This test is the deterministic,
tmux-free lock on that behaviour.

Pure in-memory: no PTY, no subprocess. Exit 0 = pass.
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core.screen_model import ScreenModel  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    if not cond:
        FAILURES.append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail and not cond else ""))


def row0(payload: str, cols: int = 60) -> str:
    m = ScreenModel(cols=cols, rows=4)
    m.feed(payload.encode())
    return m.display[0].rstrip()


print("--- text after a zero-width codepoint survives ---")

# The exact shape that motivated the fix: a menu whose entries follow an emoji.
VS16_MENU = "MENU ♀️ Settings  Quit"
check(row0(VS16_MENU + "\r\n").endswith("Settings  Quit"),
      "VS16: text after the emoji is not lost", detail=repr(row0(VS16_MENU + "\r\n")))

ZWJ_MENU = "\U0001F469‍\U0001F4BB  Developer Mode  [ENABLED]"
check("Developer Mode  [ENABLED]" in row0(ZWJ_MENU + "\r\n"),
      "ZWJ: text after the emoji sequence is not lost", detail=repr(row0(ZWJ_MENU + "\r\n")))

check(row0("x\U0001F469‍\U0001F4BBy\r\n") == "x\U0001F469‍\U0001F4BBy",
      "ZWJ: the whole grapheme cluster round-trips",
      detail=repr(row0("x\U0001F469‍\U0001F4BBy\r\n")))

# The joiner must be carried on the cell, not silently dropped: a caller doing
# its own grapheme handling needs the codepoint to still be there.
m = ScreenModel(cols=20, rows=3)
m.feed("a♀️b".encode())
check("️" in m.cell(0, 1).data,
      "VS16 is attached to the emoji's own cell", detail=repr(m.cell(0, 1).data))
# VS16 requests emoji presentation, which real terminals render two columns
# wide, so the cluster owns cell 1 + a stub at cell 2 and the next character
# lands at cell 3. Measured against tmux 3.6b: `a♀️b` puts `b` at column 3.
check(m.cell(0, 2).data == "",
      "the emoji cluster reserves a stub cell (two columns wide)",
      detail=repr(m.cell(0, 2).data))
check(m.cell(0, 3).data == "b",
      "the next character lands after the two-column cluster",
      detail=repr(m.cell(0, 3).data))

print("\n--- zero regression on the ordinary paths ---")

check(row0("\U0001F600 happy text here\r\n") == "\U0001F600 happy text here",
      "plain (non-joined) emoji unaffected")
check(row0("中文测试 abc\r\n") == "中文测试 abc",
      "CJK wide characters unaffected")
check(unicodedata.normalize("NFC", row0("éabc\r\n")) == "éabc",
      "true combining marks still compose to NFC", detail=repr(row0("éabc\r\n")))
check(row0("plain ascii line\r\n") == "plain ascii line", "plain ASCII unaffected")
check(row0("┌──┐\r\n") == "┌──┐",
      "box drawing unaffected")

# Control handling must be untouched: the intercept never sees C0/C1 or ESC, so
# escape sequences must still be parsed rather than drawn.
m = ScreenModel(cols=20, rows=4)
m.feed(b"\x1b[2;3Hmarker")
check(m.display[1].rstrip() == "  marker",
      "CSI cursor addressing still parsed, not drawn", detail=repr(m.display[1]))
check("\x1b" not in "\n".join(m.display), "no raw ESC leaked into the grid")

# A zero-width char with no preceding cell must not raise or corrupt state.
check(row0("️leading\r\n") == "leading",
      "leading zero-width char at column 0 is safe", detail=repr(row0("️leading\r\n")))

# Hashes must stay stable/int — the wait primitives depend on them.
m = ScreenModel(cols=20, rows=3)
m.feed("a♀️b\r\n".encode())
check(isinstance(m.content_hash(), int) and isinstance(m.visual_hash(), int),
      "content_hash/visual_hash still return ints")

print("\n--- IL/DL must not move the cursor column ---")
# pyte's insert_lines/delete_lines call carriage_return(), homing the cursor.
# Real terminals keep the column: `ESC[5;8H ESC[1L abc` renders at column 8 on
# both tmux 3.6b and GNU screen. A TUI that repaints a list by inserting a line
# and writing at the current column landed its text in the wrong column for us.
m = ScreenModel(cols=40, rows=10)
m.feed(b"\x1b[5;8H\x1b[1Labc")
check(m.display[4].rstrip() == "       abc",
      "IL keeps the cursor column", detail=repr(m.display[4].rstrip()))
m = ScreenModel(cols=40, rows=10)
m.feed(b"\x1b[5;8H\x1b[1Mabc")
check(m.display[4].rstrip() == "       abc",
      "DL keeps the cursor column", detail=repr(m.display[4].rstrip()))

print("\n--- half-overwriting a wide glyph destroys all of it ---")
# A terminal cannot show half a wide character: writing into either half blanks
# the whole glyph. Measured: `中` + ESC[1D + `X` renders " X" on tmux and screen.
# pyte kept the wide char AND dropped the new character, so the write vanished.
for label, payload in (("CJK", "中".encode() + b"\x1b[1DX"),
                       ("wide emoji", "\U0001F600".encode() + b"\x1b[1DX"),
                       ("VS16 cluster", "♀️".encode() + b"\x1b[1DX")):
    m = ScreenModel(cols=20, rows=4)
    m.feed(payload)
    check(m.display[0].rstrip() == " X",
          f"{label}: half-overwrite blanks the glyph and keeps the write",
          detail=repr(m.display[0].rstrip()))

print("\n--- emoji-presentation width matches a real terminal ---")
# U+2640 U+FE0F is wcwidth 1 but renders two columns wide; without accounting
# for that, one emoji shifts every following column by one.
m = ScreenModel(cols=20, rows=4)
m.feed("♀️|".encode())
check(m.cell(0, 2).data == "|",
      "VS16 cluster occupies two columns (pipe at column 2)",
      detail=repr([m.cell(0, c).data for c in range(4)]))
m = ScreenModel(cols=20, rows=4)
m.feed("♀|".encode())
check(m.cell(0, 1).data == "|",
      "a bare U+2640 (no VS16) stays one column",
      detail=repr([m.cell(0, c).data for c in range(3)]))

print("\n--- NEL and DCH match a real terminal ---")
# NEL (ESC E) is index AND carriage return, always. pyte routes it to `linefeed`,
# which only returns to column 0 under LNM, so we wrote at the old column.
m = ScreenModel(cols=20, rows=8)
m.feed(b"\x1b[2;5H\x1bE0123")
check(m.display[2].rstrip() == "0123",
      "NEL returns to column 0", detail=repr(m.display[2].rstrip()))
# ...while a plain LF must KEEP the column (HARD RULE 7).
m = ScreenModel(cols=20, rows=8)
m.feed(b"ab\ncd")
check(m.display[1].rstrip() == "  cd",
      "plain LF still keeps the column", detail=repr(m.display[1].rstrip()))

# DCH deleting a two-column glyph must remove both of its cells, or the stub
# survives as a stray blank and every following column shifts.
for label, payload, want in (("CJK", "中x".encode() + b"\r\x1b[1P", "x"),
                             ("ascii", b"abcx\r\x1b[1P", "bcx")):
    m = ScreenModel(cols=20, rows=4)
    m.feed(payload)
    check(m.display[0].rstrip() == want,
          f"DCH on {label}: whole glyph removed, no stray blank",
          detail=repr(m.display[0].rstrip()))

print("\n--- a cursor below a scroll region is not dragged into it ---")
# pyte's index() scrolls the DECSTBM region whenever the cursor matches the
# bottom margin, even when the cursor is BELOW the region entirely. Anything a
# program painted under a scroll region (a status bar, a prompt beneath a pager)
# therefore landed on the wrong rows. Measured on tmux 3.6b.
m = ScreenModel(cols=40, rows=10)
m.feed(b"\x1b[3;6r\x1b[7;37Hxxxxxxxx")   # region 3..6, wrap at row 7
rows = [i for i, line in enumerate(m.display) if line.strip()]
check(rows == [6, 7],
      "autowrap below a scroll region stays below it", detail=f"rows={rows}")
# The region itself must still scroll normally when the cursor IS inside it.
m = ScreenModel(cols=20, rows=8)
m.feed(b"\x1b[2;4r\x1b[2;1Ha\r\nb\r\nc\r\nd")
inside = [line.rstrip() for line in m.display[1:4]]
check(inside == ["b", "c", "d"],
      "a region with the cursor inside still scrolls", detail=repr(inside))
# And a plain full-screen scroll is untouched.
m = ScreenModel(cols=20, rows=5)
m.feed(b"".join(f"L{i}\r\n".encode() for i in range(8)))
check(m.display[0].rstrip() == "L4",
      "full-screen scrolling unaffected", detail=repr(m.display[0].rstrip()))

print("\n--- CUU and the right margin ---")
# pyte clamps CUU to the DECSTBM top margin even when the cursor starts outside
# the region, so a cursor below the region could not move above it.
m = ScreenModel(cols=40, rows=10)
m.feed(b"\r\n\x1b[9;10r\r\n\x1b[2A0123")
rows = [i for i, line in enumerate(m.display) if line.strip()]
check(rows == [0], "CUU from outside a region is not clamped into it",
      detail=f"rows={rows}")
# ...but the clamp must still apply while the cursor is inside the region.
m = ScreenModel(cols=20, rows=10)
m.feed(b"\x1b[3;6r\x1b[5;1H\x1b[9AX")
check(m.display[2].rstrip() == "X",
      "CUU inside a region still stops at the top margin",
      detail=repr([i for i, l in enumerate(m.display) if l.strip()]))

# A two-column glyph that cannot fit before the right margin wraps whole.
m = ScreenModel(cols=40, rows=6)
m.feed(b"\x1b[1;40H" + "\U0001F600".encode())
check(m.display[1].strip() == "\U0001F600",
      "a wide glyph with one column left wraps to the next row",
      detail=repr([(i, l.rstrip()) for i, l in enumerate(m.display) if l.strip()]))
m = ScreenModel(cols=40, rows=6)
m.feed(b"\x1b[1;39H" + "\U0001F600".encode())
check(m.display[0].rstrip().endswith("\U0001F600"),
      "a wide glyph that exactly fits does not wrap",
      detail=repr(m.display[0].rstrip()[-4:]))

print("\n--- an overwritten wide base leaves no orphaned stub ---")
# Drawing a two-column glyph over the BASE of an existing one used to leave the
# old glyph's stub stranded, so every column after it rendered one place off.
# This exact accumulation (VS16 cluster + DECSTBM change + two ICH rounds) was
# the last divergence the generative fuzz found; tmux 3.6b and GNU screen agree.
m = ScreenModel(cols=40, rows=10)
m.feed("♀️".encode() * 3 + b"\r\x1b[3@" + "│".encode() * 3
       + b"\x1b[5;7r" + "中文".encode() * 2 + b"\x1b[3@"
       + "│".encode() * 2 + "▄".encode() * 2)
check(m.display[0].rstrip() == "中文中文││▄▄",
      "overwriting a wide base leaves no stray blank",
      detail=repr(m.display[0].rstrip()))

print("\n--- alternate screen buffer (what every full-screen TUI uses) ---")
# pyte implements no alt-screen mode at all, so ESC[?1049h just set an unknown
# bit: vim/less/htop painted their alternate screen ON TOP of the main one and
# never restored it, leaving an agent reading a merged, impossible screen.
m = ScreenModel(cols=30, rows=6)
m.feed(b"main\r\n\x1b[?1049hALT")
visible = [line.rstrip() for line in m.display if line.strip()]
check(visible == ["ALT"], "entering the alt buffer hides the main screen",
      detail=repr(visible))
check(m.screen.alt_screen is True, "alt_screen reports True while active")

m = ScreenModel(cols=30, rows=6)
m.feed(b"main1\r\nmain2\r\n\x1b[?1049hALT\x1b[?1049l")
visible = [line.rstrip() for line in m.display if line.strip()]
check(visible == ["main1", "main2"], "leaving the alt buffer restores the main screen",
      detail=repr(visible))
check(m.screen.alt_screen is False, "alt_screen reports False after exit")

# 1049 saves and restores the cursor; the legacy 47/1047 modes do not.
m = ScreenModel(cols=30, rows=6)
m.feed(b"\x1b[3;5Hm\x1b[?1049hA\x1b[?1049lX")
check(m.display[2].rstrip() == "    mX", "1049 restores the saved cursor",
      detail=repr(m.display[2].rstrip()))

# The cursor is NOT homed on entry — xterm and tmux both leave it in place.
m = ScreenModel(cols=30, rows=6)
m.feed(b"main\r\n\x1b[?47hALT")
check(m.display[1].rstrip() == "ALT", "legacy mode 47 switches without homing",
      detail=repr([line.rstrip() for line in m.display[:2]]))

# Resizing WHILE on the alternate screen must clip the saved primary screen the
# same way as the live one. pyte.Screen.resize only touches self.buffer, which is
# the ALTERNATE buffer at that moment, so the saved primary screen was left at
# the old shape: the user drags the window while vim/less/htop is up (or
# drive-tui's own resize action fires) and the wrong rows come back on exit.
# The expected values are derived by resizing a screen that never entered the
# alternate buffer, so they cannot encode a defect in the clipping code itself.
def _alt_resize(payload: bytes, cols: int, rows: int,
                new_cols: int, new_rows: int, via_alt: bool) -> ScreenModel:
    mm = ScreenModel(cols=cols, rows=rows)
    mm.feed(payload)
    if via_alt:
        mm.feed(b"\x1b[?1049h")
    mm.resize(cols=new_cols, rows=new_rows)
    if via_alt:
        mm.feed(b"\x1b[?1049l")
    return mm


_ROWS_PAYLOAD = b"AAA\r\nBBB\r\nCCC\r\nDDD"
_direct = _alt_resize(_ROWS_PAYLOAD, 6, 4, 6, 2, via_alt=False)
_viaalt = _alt_resize(_ROWS_PAYLOAD, 6, 4, 6, 2, via_alt=True)
check([r.rstrip() for r in _viaalt.display] == [r.rstrip() for r in _direct.display],
      "resize on the alt screen drops saved rows from the top, as pyte does",
      detail=f"direct={[r.rstrip() for r in _direct.display]} "
             f"via_alt={[r.rstrip() for r in _viaalt.display]}")

_COLS_PAYLOAD = b"AAAAAAAA\r\nBBBBBBBB\r\nCCCCCCCC"
_direct = _alt_resize(_COLS_PAYLOAD, 8, 3, 3, 3, via_alt=False)
_viaalt = _alt_resize(_COLS_PAYLOAD, 8, 3, 3, 3, via_alt=True)
_over_direct = [y for y in range(_direct.screen.lines)
                if any(x >= 3 for x in _direct.screen.buffer[y])]
_over_viaalt = [y for y in range(_viaalt.screen.lines)
                if any(x >= 3 for x in _viaalt.screen.buffer[y])]
check(_over_viaalt == _over_direct == [],
      "resize on the alt screen leaves no over-wide cells in the saved screen",
      detail=f"direct={_over_direct} via_alt={_over_viaalt}")

print("\n--- SGR sub-parameters must not spill onto the screen ---")
# pyte's parser does not know ':' (ITU-T T.416), so it aborted the sequence and
# drew the remainder as text: ESC[4:3mU put the literal "3mU" on the grid.
# Neovim, kitty and delta all emit this routinely.
for label, payload in (("curly underline 4:3", b"\x1b[4:3mU\x1b[0m"),
                       ("underline colour 58:2", b"\x1b[58:2::255:0:0mU\x1b[0m"),
                       ("truecolor 38:2::", b"\x1b[38:2::255:0:128mU\x1b[0m")):
    m = ScreenModel(cols=20, rows=3)
    m.feed(payload)
    check(m.display[0].rstrip() == "U", f"{label}: no escape debris on screen",
          detail=repr(m.display[0].rstrip()))
# A literal colon in ordinary text must survive untouched.
m = ScreenModel(cols=20, rows=3)
m.feed(b"a:b:c")
check(m.display[0].rstrip() == "a:b:c", "literal colons in text are unaffected")


# --- alternate-screen state that must survive a resize, a RIS, and an exit ---
# All five below were found by an adversarial review of the resize fix above,
# which had clipped the saved BUFFER but left everything else attached to the
# saved CURSOR unprotected. The first is the worst class of bug in this project:
# perception silently stops updating and nothing reports a problem.

_m = ScreenModel(cols=10, rows=8)
_m.feed(b"\x1b[7;3Hx\x1b[?1049h")
_m.resize(cols=10, rows=3)          # shrink while the program owns the screen
_m.feed(b"\x1b[?1049l")
check(_m.cursor[0] < _m.rows and _m.cursor[1] < _m.cols,
      "restoring the cursor after a shrink clamps it into the screen",
      detail=f"rows={_m.rows} cols={_m.cols} cursor={_m.cursor}")
_m.feed(b"AFTER")
check(any("AFTER" in line for line in _m.display),
      "text written after that restore is still visible",
      detail=repr([line.rstrip() for line in _m.display]))

_m = ScreenModel(cols=10, rows=3)
_m.feed(b"PRIMARY\x1b[?1049hALTDATA\x1bc")
check(_m.screen.alt_screen is False,
      "RIS leaves the alternate screen",
      detail=f"alt_screen={_m.screen.alt_screen}")
_m.feed(b"NEXTPROG\x1b[?1049l")
check(any("NEXTPROG" in line for line in _m.display),
      "a rmcup after RIS does not resurrect the pre-RIS screen",
      detail=repr([line.rstrip() for line in _m.display]))

# 1049 is "save cursor as in DECSC", and DECSC saves the pen too: a TUI that
# left reverse video on must not tint what the shell writes next.
_m = ScreenModel(cols=12, rows=3)
_m.feed(b"\x1b[1;1H\x1b[?1049h\x1b[7m\x1b[?1049lshell")
check(not any(_m.cell(_m.cursor[0], x).reverse for x in range(5)),
      "the pen set inside the alternate screen does not bleed into the shell",
      detail=f"reverse={[_m.cell(_m.cursor[0], x).reverse for x in range(5)]}")

# pyte's own resize treats 0 as "unchanged"; this override must agree.
_m = ScreenModel(cols=10, rows=3)
_m.feed(b"PRIMARY-1\r\nPRIMARY-2\x1b[?1049h")
_m.resize(cols=0, rows=0)
_m.feed(b"\x1b[?1049l")
check(any("PRIMARY-1" in line for line in _m.display),
      "resize(0, 0) leaves the saved primary screen alone",
      detail=repr([line.rstrip() for line in _m.display]))


# --- the alternate screen must work whether or not pyte implements it --------
# pyte issue #90 has been open since 2017, so this class implements the feature
# itself. An upstream patch is pending, and the usual `pyte>=0.8.1` requirement
# means the day it ships in a release every installation picks it up -- at which
# point BOTH layers would switch and the primary screen would restore blank on
# every full-screen program exit. `_Screen._PYTE_HAS_ALT` decides which layer
# does the work.
#
# What is asserted here is deterministic under whichever pyte is installed: the
# flag agrees with the base class, and the round trip works either way. The
# cross-version case is additionally verified by hand against a patched pyte
# checkout -- a monkeypatch of the real base class would be exactly the
# self-satisfying harness HARD RULE 5 forbids, so the logic is instead exercised
# through a stand-in base class below.
import pyte as _pyte  # noqa: E402
from smartcli_core.screen_model import _Screen  # noqa: E402

check(_Screen._PYTE_HAS_ALT == hasattr(_pyte.Screen, "alternate_screen"),
      "the pyte-capability flag matches the installed pyte",
      detail=f"flag={_Screen._PYTE_HAS_ALT} "
             f"base={hasattr(_pyte.Screen, 'alternate_screen')}")

_m = ScreenModel(cols=14, rows=3)
_m.feed(b"SHELL-1\r\nSHELL-2")
_before = [line.rstrip() for line in _m.display]
_m.feed(b"\x1b[?1049hPAGER")
_alt_in = _m.screen.alt_screen
_m.feed(b"\x1b[?1049l")
check([line.rstrip() for line in _m.display] == _before,
      "the alt-screen round trip restores the primary screen exactly",
      detail=f"before={_before} after={[l.rstrip() for l in _m.display]}")
check(_alt_in and not _m.screen.alt_screen,
      "alt_screen reads True inside and False after, whichever layer switched",
      detail=f"inside={_alt_in} after={_m.screen.alt_screen}")

# Exercise the branch the installed pyte does NOT take. The inheritance chain
# stays REAL (a genuine _Screen subclass over the installed pyte.Screen); only
# the capability flag is overridden, and nothing is monkeypatched -- the
# observation is the state _enter_alt would have written. A fabricated base class
# was tried first and broke zero-argument super(), which is a fair warning that
# it was too far from the real path to prove anything.
class _CapableProbe(_Screen):
    _PYTE_HAS_ALT = True


_probe = _CapableProbe(8, 2)
_probe.set_mode(1049, private=True)
_switched = _probe._alt_active or _probe._saved_main is not None
_probe.reset_mode(1049, private=True)
check(not _switched and not _probe._alt_active,
      "with a capable base class the subclass does not switch as well",
      detail=f"_alt_active={_probe._alt_active} "
             f"_saved_main_set={_probe._saved_main is not None}")

if FAILURES:
    print(f"\ntest_terminal_fidelity FAIL -- {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("\nPASS: every measured real-terminal divergence stays fixed; no regressions.")
sys.exit(0)
