#!/usr/bin/env python3
"""test_terminal_modes.py — the terminal-mode set is CLOSED and queryable by NAME.

Before this file there was no mode API at all. Two facts were reachable, as two
hand-written properties with their own private decoding of pyte's storage:
``ScreenModel.app_cursor`` (``1 << 5 in screen.mode``) and ``ScreenModel.
alt_screen``. Everything else pyte branches on while parsing — DECAWM, DECOM,
DECSCNM, DECCOLM, IRM, LNM, DECTCEM — had NO name and NO query, so an agent
that wanted "is the program in origin mode" had to reach into the pyte object
and re-derive the ``<< 5`` shift itself.

That is now one closed registry: :class:`Mode` names the set, ``MODE_REGISTRY``
says where each answer lives, and ``ScreenModel.mode(name)`` /
``ScreenModel.modes()`` read it. The point of *closed* is that an unknown name
raises instead of answering ``False`` — a typo that reads as "that mode is off"
is the failure mode this removes, and it is the reason ``mode()`` is strict.

The two pre-existing properties are preserved as wrappers and pinned below, so
this is an addition and not a migration: ``PtySession.send_keys`` reads
``app_cursor`` on every keypress and the snapshot builder reads ``alt_screen``.

Pure in-memory: no PTY, no subprocess. Exit 0 = pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyte  # noqa: E402
from pyte import modes as mo  # noqa: E402

from smartcli_core.screen_model import (  # noqa: E402
    MODE_REGISTRY,
    Mode,
    ModeSpec,
    ScreenModel,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    if not cond:
        FAILURES.append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail and not cond else ""))


def fed(*payloads: bytes, cols: int = 20, rows: int = 4) -> ScreenModel:
    """A model that has been fed each payload in turn (one session, in order)."""
    m = ScreenModel(cols=cols, rows=rows)
    for p in payloads:
        m.feed(p)
    return m


# --- the set is closed: one spec per member, and only members --------------
print("--- the mode set is closed ---")

check(set(MODE_REGISTRY) == set(Mode),
      "every Mode member has a registry entry and vice versa",
      detail=f"members-only={sorted(m.value for m in set(Mode) - set(MODE_REGISTRY))} "
             f"specs-only={sorted(str(m) for m in set(MODE_REGISTRY) - set(Mode))}")

# A member with no spec would make mode() a KeyError only at query time, and a
# spec for a non-member would be unreachable. Both are structural, so the check
# above is exact rather than a count.
check(len(MODE_REGISTRY) == len(Mode),
      "no duplicate/aliased entries hide a member",
      detail=f"{len(MODE_REGISTRY)} specs vs {len(Mode)} members")

# Reading the whole registry must not be able to mutate it: it is the one place
# the numbers live, so a caller writing into it would silently repoint every
# query in the process.
try:
    MODE_REGISTRY[Mode.AUTOWRAP] = ModeSpec((99,))  # type: ignore[index]
    check(False, "MODE_REGISTRY rejects writes (it is a read-only mapping)")
except TypeError:
    check(True, "MODE_REGISTRY rejects writes (it is a read-only mapping)")

print("\n--- unknown names raise instead of answering False ---")

m = fed(b"\x1b[?1h")   # DECCKM on: the closest thing to a "mode is on" screen
for bad in ("decckm", "alt_screens", "APP_CURSOR", "", "1049", "app cursor"):
    try:
        got = m.mode(bad)
        check(False, f"mode({bad!r}) raises rather than answering {got!r}")
    except ValueError:
        check(True, f"mode({bad!r}) raises rather than answering False")
    except KeyError:
        check(False, f"mode({bad!r}) raised KeyError (registry miss), not ValueError")

# The closedness is a property of the type, not of the caller's discipline: a
# member value and its plain string must be interchangeable.
check(m.mode(Mode.APP_CURSOR) is m.mode("app_cursor"),
      "a Mode member and its string value answer identically")
check(Mode.ALT_SCREEN == "alt_screen",
      "Mode is a str enum, so names compare equal to their literal")
check(repr(Mode.ALT_SCREEN) == "Mode.ALT_SCREEN",
      "repr names the member (not the opaque enum default)",
      detail=repr(Mode.ALT_SCREEN))

print("\n--- every mode answers by name from the sequences that set it ---")

# (name, the sequence that sets it, the sequence that resets it, extra numbers
# that must also report it). The "extra" column is what makes this a real table
# rather than a loop over the registry: a mode whose alternate entry numbers were
# dropped from ModeSpec would answer False here.
CASES = [
    ("app_cursor",     b"\x1b[?1h",   b"\x1b[?1l",   []),
    ("autowrap",       b"\x1b[?7h",   b"\x1b[?7l",   []),
    ("column_132",     b"\x1b[?3h",   b"\x1b[?3l",   []),
    ("cursor_visible", b"\x1b[?25h",  b"\x1b[?25l",  []),
    ("insert_mode",    b"\x1b[4h",    b"\x1b[4l",    []),
    ("newline_mode",   b"\x1b[20h",   b"\x1b[20l",   []),
    ("origin",         b"\x1b[?6h",   b"\x1b[?6l",   []),
    ("reverse_video",  b"\x1b[?5h",   b"\x1b[?5l",   []),
    # 47 and 1047 enter the alternate buffer without the cursor save 1049 does.
    ("alt_screen",     b"\x1b[?1049h", b"\x1b[?1049l", [b"\x1b[?1047h", b"\x1b[?47h"]),
]

# pyte powers up with DECAWM and DECTCEM set — that is its _DEFAULT_MODE, and a
# real terminal does the same (line wrap and a visible cursor). So "off until a
# program asks" is true of only seven of the nine modes, and a registry that
# reported every mode as off would still look plausible on the other seven.
DEFAULT_ON = frozenset({"autowrap", "cursor_visible"})

for name, on, off, also_on in CASES:
    check(fed().mode(name) == (name in DEFAULT_ON),
          f"{name} is {'on' if name in DEFAULT_ON else 'off'} on a fresh screen "
          f"(pyte's power-on state)",
          detail=f"got={fed().mode(name)}")

    m_on = fed(on)
    check(m_on.mode(name), f"mode({name!r}) is True after its set sequence")

    # The set sequence must be visible through modes() too, or the two APIs
    # disagree about the same screen.
    check(Mode(name) in m_on.modes(),
          f"modes() includes {name!r} on the same screen mode({name!r}) reports on")

    # Reset turns the mode OFF, which is NOT the same as returning to the
    # power-on state: ESC[?7l really does stop a terminal from wrapping until
    # something sets it again. Asserting "back to default" here would have
    # demanded the opposite of what the sequence does.
    # For the alternate screen the reset is the 1049 form whichever entry number
    # went in, because that is what a well-behaved program sends to leave.
    check(not fed(on, off).mode(name),
          f"mode({name!r}) is False again after its reset sequence",
          detail=f"got={fed(on, off).mode(name)}")

    for extra in also_on:
        check(fed(extra).mode(name),
              f"mode({name!r}) is also True for its alternate entry {extra!r}")

print("\n--- private vs ANSI: the shift is real and is read from pyte ---")

# Where pyte exports a constant, the registry bit must equal it. If the << 5
# were applied wrongly the query would still "work" — it would just read a bit
# no program ever sets, and answer False forever.
for mode_name, constant in (
    (Mode.AUTOWRAP, mo.DECAWM),
    (Mode.COLUMN_132, mo.DECCOLM),
    (Mode.ORIGIN, mo.DECOM),
    (Mode.REVERSE_VIDEO, mo.DECSCNM),
):
    check(MODE_REGISTRY[mode_name].bit == constant,
          f"{mode_name.value}.bit == pyte's {constant}",
          detail=f"bit={MODE_REGISTRY[mode_name].bit} want={constant}")

# The ANSI (non-private) modes are stored unshifted, and the two encodings must
# not collide: a naive "always shift by five" would make INSERT_MODE read mode 4
# private (128), which no program sets.
check(MODE_REGISTRY[Mode.INSERT_MODE].bit == mo.IRM,
      "INSERT_MODE is unshifted (pyte.IRM)",
      detail=f"bit={MODE_REGISTRY[Mode.INSERT_MODE].bit} want={mo.IRM}")
check(MODE_REGISTRY[Mode.NEWLINE_MODE].bit == mo.LNM,
      "NEWLINE_MODE is unshifted (pyte.LNM)",
      detail=f"bit={MODE_REGISTRY[Mode.NEWLINE_MODE].bit} want={mo.LNM}")
check(MODE_REGISTRY[Mode.INSERT_MODE].bit != mo.IRM << 5,
      "the ANSI and DEC encodings of mode 4 are distinct bits")

# And the sequences really do set those distinct bits — pyte stores 4 for the
# ANSI form and 4 << 5 for the private one.
check(mo.IRM in fed(b"\x1b[4h").screen.mode,
      "ESC[4h sets the unshifted IRM bit pyte reports")
check((mo.IRM << 5) not in fed(b"\x1b[4h").screen.mode,
      "ESC[4h does NOT set the shifted bit (they are not interchangeable)")

# DECTCEM is the one private mode read from the cursor rather than the bit, so
# pin that the two agree in the state that matters: hidden.
check(MODE_REGISTRY[Mode.CURSOR_VISIBLE].numbers == (25,),
      "CURSOR_VISIBLE is DECTCEM (25) even though it reads the cursor",
      detail=str(MODE_REGISTRY[Mode.CURSOR_VISIBLE].numbers))
check(fed(b"\x1b[?25l").cursor_hidden and not fed(b"\x1b[?25l").mode("cursor_visible"),
      "a hidden cursor reads as cursor_visible=False")

print("\n--- the alternate screen is answered from the BUFFER, not the bit ---")

# pyte records a bit for 1047 and never clears it, so "?1047h then ?1049l"
# leaves 1047's bit set while the primary buffer is already back. A registry
# that read the bit here would report alt_screen forever after.
stale = fed(b"\x1b[?1047h", b"\x1b[?1049l")
check(not stale.alt_screen,
      "leaving the alternate screen is seen even when a stale 1047 bit remains",
      detail=f"bits={sorted(stale.screen.mode)} alt_screen={stale.alt_screen}")
check(not stale.mode("alt_screen"),
      "mode('alt_screen') agrees with .alt_screen on that same screen")

# And the reverse: a stale bit must not make a never-entered alternate screen
# look active after an unrelated reset.
check(not fed(b"\x1b[?1047h", b"\x1bc").alt_screen,
      "RIS leaves the alternate screen (mode 'alt_screen' follows)")

print("\n--- the pre-existing properties are preserved ---")

# PtySession.send_keys reads app_cursor on every keypress; the snapshot builder
# reads alt_screen, cursor_hidden and base_reverse. If any of these changed
# spelling or meaning, driving and perceiving would change silently.
for prop, name in (("app_cursor", "app_cursor"),
                   ("alt_screen", "alt_screen"),
                   ("base_reverse", "reverse_video")):
    for payload in ((), (b"\x1b[?1h",), (b"\x1b[?1049h",), (b"\x1b[?5h",),
                    (b"\x1b[?1h\x1b[?1049h\x1b[?5h\x1b[?25l",)):
        model = fed(*payload)
        check(getattr(model, prop) == model.mode(name),
              f".{prop} and mode({name!r}) agree",
              detail=f"payload={payload!r} prop={getattr(model, prop)} "
                     f"mode={model.mode(name)}")

check(fed(b"\x1b[?25l").cursor_hidden and not fed(b"\x1b[?25l").mode("cursor_visible"),
      ".cursor_hidden is the negation of mode('cursor_visible')")
check(not fed().cursor_hidden and fed().mode("cursor_visible"),
      ".cursor_hidden is False for a visible cursor (default)")

# base_reverse changed WHERE it reads (screen.default_char.reverse -> the DECSCNM
# bit), so pin it across a full set/reset cycle rather than only at rest: a
# snapshot taken between the two reads its highlight baseline from this, and a
# screen that painted reverse cells and then cleared the mode must not keep
# reporting a reverse baseline.
for label, seq, want in (
        ("before", (), False),
        ("after 5h", (b"\x1b[?5h",), True),
        ("after 5h then 5l", (b"\x1b[?5h", b"\x1b[?5l"), False),
        ("after 5l only", (b"\x1b[?5l",), False),
        ("after RIS", (b"\x1b[?5h", b"\x1bc"), False)):
    model = fed(*seq)
    check(model.base_reverse is want and model.mode("reverse_video") is want,
          f".base_reverse is {want} {label}",
          detail=f"base_reverse={model.base_reverse} mode={model.mode('reverse_video')}")
    check(model.base_reverse == bool(model.screen.default_char.reverse),
          f".base_reverse still matches pyte's own default_char.reverse {label}",
          detail=f"prop={model.base_reverse} "
                 f"default_char={model.screen.default_char.reverse}")

print("\n--- modes(): the whole set at once ---")

fresh = fed()
check(fresh.modes() == frozenset({Mode.AUTOWRAP, Mode.CURSOR_VISIBLE}),
      "a fresh screen reports exactly pyte's default modes (DECAWM, DECTCEM)",
      detail=str(sorted(x.value for x in fresh.modes())))

everything = fed(b"\x1b[?1h\x1b[?1049h\x1b[?25l\x1b[?5h\x1b[4h\x1b[20h\x1b[?6h")
check(everything.modes() == frozenset({
    Mode.APP_CURSOR, Mode.ALT_SCREEN, Mode.AUTOWRAP, Mode.INSERT_MODE,
    Mode.NEWLINE_MODE, Mode.ORIGIN, Mode.REVERSE_VIDEO,
}), "modes() reports every enabled mode and no disabled one",
    detail=str(sorted(x.value for x in everything.modes())))

check(everything.modes() <= set(Mode),
      "modes() only ever returns members of the closed set")

# The two APIs must never disagree, mode by mode, on a screen with most of them
# flipped — a modes() that omitted one entry would pass the set comparison above
# only if that entry were also missing from the expected set.
for member in Mode:
    check((member in everything.modes()) == everything.mode(member),
          f"modes() and mode() agree on {member.value}")

check(isinstance(everything.modes(), frozenset),
      "modes() returns a frozenset (a caller cannot mutate shared state)")

print("\n--- modes that change what the screen MEANS still work through it ---")

# These are the reasons the modes exist at all: each one silently changes how
# later bytes are interpreted, so a query that did not track them would report a
# screen that never said what it appears to say.
wrap_off = fed(b"\x1b[?7l" + b"x" * 25)
check(not wrap_off.mode("autowrap") and wrap_off.display[1].strip() == "",
      "DECAWM off: the overlong line does not wrap",
      detail=repr(wrap_off.display[1][:8]))
check(fed(b"\x1b[?7h" + b"x" * 25).mode("autowrap")
      and fed(b"\x1b[?7h" + b"x" * 25).display[1].strip() == "x" * 5,
      "DECAWM on: the same bytes wrap to the next row")

# DECSCNM must reach the cells, not just the query: the highlight baseline in
# snapshot.py is measured against it.
rev = fed(b"\x1b[?5h", b"hi")
check(rev.mode("reverse_video") and rev.base_reverse and rev.cell(0, 0).reverse,
      "DECSCNM on: the mode, the baseline and the cells all agree")
check(not fed(b"\x1b[?5h", b"hi", b"\x1b[?5l").cell(0, 0).reverse,
      "DECSCNM off again: cells lose reverse, so a highlight read is honest")

# DECCOLM changes the geometry, which is observable without any query at all.
check(fed(b"\x1b[?3h").cols == 132 and fed(b"\x1b[?3h").mode("column_132"),
      "DECCOLM on: the screen really is 132 columns and says so")
check(fed(b"\x1b[?3h", b"\x1b[?3l").cols == 20,
      "DECCOLM off: the original width is restored")

# LNM changes what a bare LF does; IRM changes how a write lands.
check(fed(b"\x1b[20h", b"a\nb").display[1].startswith("b"),
      "LNM on: LF returns to column 0",
      detail=repr(fed(b"\x1b[20h", b"a\nb").display[1][:4]))
check(not fed(b"a\nb").display[1].startswith("b"),
      "LNM off (default): the same LF leaves the column alone",
      detail=repr(fed(b"a\nb").display[1][:4]))

ins = fed(b"\x1b[4habc", b"\x1b[1;1HX")
check(ins.mode("insert_mode") and ins.display[0].rstrip() == "Xabc",
      "IRM on: the write shifts the line instead of overwriting it",
      detail=repr(ins.display[0][:6]))
check(fed(b"abc", b"\x1b[1;1HX").display[0].rstrip() == "Xbc",
      "IRM off (default): the same write overwrites")

# Origin mode makes addressing relative to the scroll region.
# Assert on the GRID, not the cursor: writing X advances the cursor to column 1,
# so the cursor position alone would not distinguish "landed on the margin" from
# "landed on row 0" as cleanly as looking at where the glyph is.
org = fed(b"\x1b[3;7r", b"\x1b[?6h", b"\x1b[1;1HX")
check(org.mode("origin")
      and org.display[2].startswith("X") and not org.display[0].startswith("X"),
      "DECOM on: row 1 addresses the top margin, not row 0",
      detail=f"row0={org.display[0][:3]!r} row2={org.display[2][:3]!r}")

# With no scroll region set there is no margin to be relative to, so DECOM is
# reported but addresses absolutely — the query must not imply otherwise.
nomargin = fed(b"\x1b[?6h", b"\x1b[1;1HX")
check(nomargin.mode("origin") and nomargin.display[0].startswith("X"),
      "DECOM with no DECSTBM set still addresses row 0",
      detail=f"row0={nomargin.display[0][:3]!r}")

# Without DECOM the same bytes land on row 0 even with margins set: that
# difference is exactly what the mode names, so the two screens above are only
# distinguishable by asking.
noorigin = fed(b"\x1b[3;7r", b"\x1b[1;1HX")
check(not noorigin.mode("origin") and noorigin.display[0].startswith("X"),
      "without DECOM the same addressing is absolute",
      detail=f"row0={noorigin.display[0][:3]!r}")

print("\n--- the registry is the only place the numbers live ---")

# A mode read from the wrong place is indistinguishable from a mode that is
# simply never set, so each entry has to state where its answer comes from:
# only the two that are not a bit in Screen.mode may carry a probe.
check(MODE_REGISTRY[Mode.ALT_SCREEN].probe is not None,
      "ALT_SCREEN reads the live buffer (pyte's 1047 bit is not the state)")
check(MODE_REGISTRY[Mode.CURSOR_VISIBLE].probe is not None,
      "CURSOR_VISIBLE reads the cursor")
for member in Mode:
    if member not in (Mode.ALT_SCREEN, Mode.CURSOR_VISIBLE):
        check(MODE_REGISTRY[member].probe is None,
              f"{member.value} is read from the Screen.mode bit")

# bit() refuses a multi-number spec: ALT_SCREEN has three entry numbers and no
# single bit, and silently collapsing them to one would report a mode that is
# never set as permanently on.
try:
    _ = MODE_REGISTRY[Mode.ALT_SCREEN].bit
    check(False, "ALT_SCREEN has no single Screen.mode bit to report")
except ValueError:
    check(True, "ALT_SCREEN has no single Screen.mode bit to report")

# ALT_SCREEN is read from an attribute OURS (or a future pyte's), so resolving
# it against a stock pyte.Screen has to answer "no alternate buffer" rather
# than raise AttributeError — ModeSpec.resolve is typed for pyte.Screen, and a
# caller holding one must still get an answer. The same goes for a mode read
# from the cursor. Both would otherwise be latent crashes in a query that looks
# total.
stock = pyte.Screen(20, 4)
check(not MODE_REGISTRY[Mode.ALT_SCREEN].resolve(stock),
      "ALT_SCREEN resolves to False on a stock pyte.Screen (no such attribute)")
check(MODE_REGISTRY[Mode.CURSOR_VISIBLE].resolve(stock),
      "CURSOR_VISIBLE resolves against a stock pyte.Screen's cursor")
check(MODE_REGISTRY[Mode.AUTOWRAP].resolve(stock),
      "a bit-backed mode resolves against a stock pyte.Screen too")

print("\n--- a mode query must not disturb the screen it reads ---")

# mode() is called from a driving loop and from snapshot building, often while
# other state is being read. Reading a mode twice, or reading all of them, has to
# leave the grid, the cursor and the mode set exactly as they were — otherwise a
# perception call becomes a mutation.
before_model = fed(b"\x1b[?1h\x1b[?1049h\x1b[?5h", b"hello")
before = (before_model.content_hash(), before_model.cursor,
          before_model.cursor_hidden, tuple(before_model.display),
          sorted(before_model.screen.mode))
before_model.modes()
before_model.mode(Mode.ALT_SCREEN)
for member in Mode:
    before_model.mode(member)
after = (before_model.content_hash(), before_model.cursor,
         before_model.cursor_hidden, tuple(before_model.display),
         sorted(before_model.screen.mode))
check(before == after,
      "reading every mode leaves the grid, cursor and mode set untouched",
      detail=f"{before!r} -> {after!r}")

if FAILURES:
    print(f"\ntest_terminal_modes FAIL -- {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("\nPASS: the mode set is closed, queryable by name, and still means what it did.")
sys.exit(0)
