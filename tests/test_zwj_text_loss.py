#!/usr/bin/env python3
"""test_zwj_text_loss.py — regression lock: a zero-width joiner must not eat the line.

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
check(m.cell(0, 2).data == "b",
      "the next character lands in the next cell", detail=repr(m.cell(0, 2).data))

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

if FAILURES:
    print(f"\ntest_zwj_text_loss FAIL -- {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("\nPASS: zero-width joiners no longer truncate a line; no regressions.")
sys.exit(0)
