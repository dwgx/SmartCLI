#!/usr/bin/env python3
"""test_cell_span_and_split_sgr.py — locks T05 (cell-span CJK slicing) and T04
(SGR colon sub-parameters split across feed() boundaries).

T05: Snapshot's highlighted-span text used a Python string slice
(``display[y][a:b]``) where ``a``/``b`` are terminal CELL columns, not string
indices. A wide character (CJK, emoji, fullwidth digits) is one character but
two cells, so any span to the right of one was misaligned -- a 3-item Chinese
menu with item 2 in reverse video reported ``selected.text == '3'`` where the
highlighted label is ``'保存'``.

T04: ``_ByteStream.feed()``'s colon-SGR pre-pass (``screen_model.py``) is a
regex over whatever bytes a single ``feed()`` call receives. SGR sub-parameters
use ':' (ITU-T T.416): ``ESC[4:3m`` is a curly underline, ``ESC[38:2::R:G:Bm``
a truecolor foreground. A read boundary landing inside one of these -- which a
real PTY does often, since reads are chunked at the OS's discretion -- means
neither half contains the whole ``ESC[...m`` sequence, so the regex never
matches, the colon reaches pyte unrewritten, and pyte draws the remainder as
text.

Pure in-memory: no PTY, no subprocess. Exit 0 = pass.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core.screen_model import ScreenModel  # noqa: E402
from smartcli_core.snapshot import build_snapshot  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    if not cond:
        FAILURES.append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail and not cond else ""))


def cell_span_text(model: ScreenModel, row: int, a: int, b: int) -> str:
    """Ground truth for a highlighted span: aggregate cell DATA over [a, b),
    not a Python string slice of the rendered line."""
    cells = model.row_cells(row)
    return "".join(c.data for c in cells[a:b]).strip()


# ============================================================ T05 ==========
print("--- T05: highlighted-span text must use cell columns, not string subscripts ---")

# The exact end-to-end acceptance case: a 3-item Chinese menu, item 2 highlighted.
m = ScreenModel(cols=40, rows=5)
m.feed("  1) 打开   2) \x1b[7m保存\x1b[0m   3) 退出\n".encode("utf-8"))
snap = build_snapshot(m)
check(snap.selected is not None and snap.selected.text == "保存",
      "acceptance: reverse-video '保存' reports as '保存', not '3'",
      detail=f"selected={snap.selected!r}")

for s in snap.menu_items:
    truth = cell_span_text(m, s.row, s.col_start, s.col_end)
    check(s.text == truth, f"menu span r{s.row}[{s.col_start}:{s.col_end}] matches cell truth",
          detail=f"reported={s.text!r} truth={truth!r}")

# A wide character LEFT of the highlighted span must not shift the result, for
# every wide-character family the reproduction found broken (CJK, Japanese,
# emoji, fullwidth digits); ASCII and a highlight that itself starts with a
# wide character are regression guards (the string-slice bug happened to get
# both of those right, since there is no leading shift to misalign).
_CASES = (
    # (label, payload, expected span text)
    ("CJK prefix", "中文 \x1b[7mOK\x1b[0m", "OK"),
    ("Japanese + ASCII", "日本語テスト \x1b[7mOK\x1b[0m", "OK"),
    ("emoji before", "🚀🚀 \x1b[7mOK\x1b[0m", "OK"),
    ("full-width digits", "１２３\x1b[7mOK\x1b[0m", "OK"),
    ("pure ASCII", "abcdefgh \x1b[7mOK\x1b[0m", "OK"),
    ("wide character inside the span", "\x1b[7m中文OK\x1b[0m", "中文OK"),
)
for label, payload, want in _CASES:
    mm = ScreenModel(cols=40, rows=3)
    mm.feed(payload.encode("utf-8"))
    ssnap = build_snapshot(mm)
    assert ssnap.menu_items, f"{label}: fixture produced no highlighted span at all"
    span = ssnap.menu_items[0]
    truth = cell_span_text(mm, span.row, span.col_start, span.col_end)
    check(span.text == truth, f"{label}: span text == cell-aggregated truth",
          detail=f"reported={span.text!r} truth={truth!r}")
    check(span.text == want, f"{label}: span text is {want!r} (no leading-shift corruption)",
          detail=f"reported={span.text!r}")


# ============================================================ T04 ==========
print("\n--- T04: SGR colon sub-parameters must survive any feed() split point ---")

_COLON_PAYLOADS = {
    "curly underline": b"\x1b[4:3mX",
    "truecolor fg": b"\x1b[38:2::255:0:0mX",
    "truecolor bg": b"\x1b[48:2::0:255:0mX",
    "underline colour": b"\x1b[58:2::1:2:3mX",
}
_CONTROL_PAYLOADS = {
    "plain SGR (control)": b"\x1b[31mX",
    "CSI cursor move (control)": b"\x1b[10;5HX",
    "OSC title (control)": b"\x1b]0;hello\x07X",
}

for label, payload in {**_COLON_PAYLOADS, **_CONTROL_PAYLOADS}.items():
    ref = ScreenModel(cols=30, rows=3)
    ref.feed(payload)
    ref_line = ref.display[0]

    bad_cuts = []
    for cut in range(1, len(payload)):
        s = ScreenModel(cols=30, rows=3)
        s.feed(payload[:cut])
        s.feed(payload[cut:])
        if s.display[0] != ref_line:
            bad_cuts.append(cut)
    check(not bad_cuts, f"{label}: split-safe at every byte boundary ({len(payload) - 1} cuts)",
          detail=f"diverging cuts={bad_cuts} reference={ref_line!r}")

    bw = ScreenModel(cols=30, rows=3)
    for i in range(len(payload)):
        bw.feed(payload[i:i + 1])
    check(bw.display[0] == ref_line, f"{label}: identical when fed one byte at a time",
          detail=f"got={bw.display[0]!r} want={ref_line!r}")

    check(ref.feed_errors == 0 and bw.feed_errors == 0,
          f"{label}: feed_errors stays 0 for a valid stream",
          detail=f"whole={ref.feed_errors} bytewise={bw.feed_errors}")

# A literal colon in plain text, split right at the colon, must still survive.
m = ScreenModel(cols=20, rows=3)
m.feed(b"a:b:")
m.feed(b"c")
check(m.display[0].rstrip() == "a:b:c", "literal colon split across feed() is unaffected")

print("\n--- T04: chunk-size sweep on a realistic mixed CJK + truecolor stream ---")
# Same shape as the stream that quantified the defect: every line carries one
# truecolor and one curly-underline SGR (the Neovim/kitty/delta-style output
# the colon pre-pass exists for).
STREAM = "".join(
    f"\x1b[38:2::{i * 7 % 256}:0:0m行{i} 中文内容\x1b[0m "
    f"\x1b[4:3m下划线\x1b[0m ok\n"
    for i in range(200)
).encode("utf-8")

ref = ScreenModel(cols=80, rows=24)
ref.feed(STREAM)
ref_text = ref.screen.display
check(ref.feed_errors == 0, "reference (unsplit) stream parses with feed_errors == 0")

# 1 KB and 4 KB are the exact chunk sizes the reproduction measured as 100%
# and 78% corrupted before this fix; 65536 exceeds the whole stream (sanity
# check that a single, unsplit feed is unaffected by the split-detection path).
for chunk in (1, 64, 1024, 4096, 65536):
    bad = 0
    err_hits = 0
    trials = 20
    for seed in range(trials):
        rng = random.Random(seed)
        mm = ScreenModel(cols=80, rows=24)
        i = 0
        while i < len(STREAM):
            n = rng.randint(1, chunk)
            mm.feed(STREAM[i:i + n])
            i += n
        if mm.screen.display != ref_text:
            bad += 1
        if mm.feed_errors != 0:
            err_hits += 1
    check(bad == 0, f"chunk<={chunk:>6} bytes: 0/{trials} streams corrupted",
          detail=f"corrupted={bad}/{trials}")
    check(err_hits == 0, f"chunk<={chunk:>6} bytes: feed_errors stays 0 across all trials",
          detail=f"trials with feed_errors!=0: {err_hits}/{trials}")

print("\n--- feed_errors still fires on a genuinely malformed sequence (not just a split) ---")
# ESC[;@ dispatches insert/delete-characters with an empty leading numeric
# parameter -> wrong arity -> pyte raises (see ScreenModel.feed's docstring).
# Unrelated to colons: proves the split-detection buffering does not swallow
# or delay a real parse failure.
m = ScreenModel(cols=20, rows=3)
before = m.feed_errors
m.feed(b"\x1b[;@")
check(m.feed_errors == before + 1, "a genuinely malformed control sequence still bumps feed_errors",
      detail=f"feed_errors={m.feed_errors}")

print("\n--- the held tail stays bounded on an unterminated parameter run (T04) ---")
# The split buffer must not become an unbounded sink: a stream that parks on
# "ESC[" and then keeps sending parameter bytes has no terminating byte, so a
# hold-everything rule would grow _pending for as long as the stream lasts.
# Past the cap the tail is forwarded instead (pyte then aborts it), which is the
# pre-buffering behaviour for a run no real program emits.
m = ScreenModel(cols=30, rows=3)
m.feed(b"\x1b[")
for _ in range(64):                      # 256 KB of digits, never terminated
    m.feed(b"9" * 4096)
held = len(m.stream._pending)
check(held <= m.stream._MAX_PENDING,
      f"held tail is bounded ({held} <= {m.stream._MAX_PENDING} bytes after 256 KB)",
      detail=f"_pending={held}")
m.feed(b"m")                             # terminate the flooded run, as pyte would see it
m.feed(b"\x1b[4:3mZ")                    # a fresh, valid colon SGR afterwards
check(m.display[0].rstrip().endswith("Z"), "stream recovers: a later colon SGR still renders its text",
      detail=f"display={m.display[0]!r}")
check("3m" not in m.display[0], "stream recovers: no escape debris from the later sequence",
      detail=f"display={m.display[0]!r}")


if FAILURES:
    print(f"\ntest_cell_span_and_split_sgr FAIL -- {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("\nPASS: cell-span slicing and split SGR colon parameters are both correct.")
sys.exit(0)
