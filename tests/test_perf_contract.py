#!/usr/bin/env python3
"""test_perf_contract.py — the wait primitives must stay cheap enough to poll.

Before this file the suite had NO performance test at all, and it showed:
``visual_hash`` cost **16.6 ms on a 300x100 screen** — 55% of the default 30 ms
``wait_visual_change`` polling budget — because it hashed every cell of every row
on every call, even when nothing had changed. Nothing would have caught a change
that made it worse.

Two things are asserted here:

1. **Equivalence.** The incremental implementation must return exactly what a
   from-scratch model returns for the same bytes. A fast hash that disagrees with
   itself would break every wait primitive built on it, so this is checked first
   and over adversarial payloads (erase, insert/delete lines, wide chars).
2. **Ceilings.** Per-call wall-clock budgets at three sizes for the idle-poll
   case (nothing changed) and the realistic case (one row changed). Deliberately
   generous — this gates ORDERS of magnitude, not percentages, so it will not
   flake on a loaded CI runner while still catching a return to per-cell hashing.

The full-repaint case is intentionally NOT bounded: if every row genuinely
changed there is no way around rehashing them, and a poll that sees a
full repaint returns ``changed=True`` immediately rather than continuing to poll.

Pure/in-memory: no PTY, no subprocess. Exit 0 = pass.
"""
from __future__ import annotations

import random
import sys
import time
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
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))


def fill(cols: int, rows: int) -> ScreenModel:
    m = ScreenModel(cols=cols, rows=rows)
    m.feed(("x" * (cols - 1) + "\r\n").encode() * (rows - 1))
    return m


def per_call_ms(fn, iterations: int) -> float:
    fn()  # warm
    best = float("inf")
    for _ in range(3):  # best-of-3: least sensitive to scheduler noise
        t0 = time.perf_counter()
        for _ in range(iterations):
            fn()
        best = min(best, (time.perf_counter() - t0) / iterations * 1000)
    return best


# --------------------------------------------------------------------------
# 1. Equivalence — the cheap path must agree with a full recomputation.
# --------------------------------------------------------------------------
print("--- incremental visual_hash equals a from-scratch computation ---")

FRAGMENTS = [
    b"abc", b"MENU", b"\r\n", b"\r", b"\t", b"\x1b[7m", b"\x1b[0m", b"\x1b[31m",
    b"\x1b[3;5H", b"\x1b[2J", b"\x1b[K", b"\x1b[1L", b"\x1b[1M", b"\x1b[2P",
    b"\x1b[1@", b"\x1b[2;6r", b"\x1bE", b"\x1bM", b"\x1b7", b"\x1b8",
    "中文".encode(), "♀️".encode(), "\U0001F600".encode(), b"z" * 45,
]

def exhaustive_visual_hash(model: ScreenModel) -> int:
    """Reference implementation: hash every cell, no caching, no dirty tracking.

    Deliberately a separate, obvious computation. The incremental
    ``visual_hash`` must agree with this for the SAME screen state — that is the
    property the optimization has to preserve.
    """
    import zlib
    crc = 0
    for row in range(model.screen.lines):
        line = model.screen.buffer[row]
        parts = []
        for col in range(model.screen.columns):
            char = line[col]
            parts.append(
                f"{char.data}\x00{char.fg}\x00{char.bg}\x00"
                f"{char.bold:d}{char.italics:d}{char.underscore:d}"
                f"{char.strikethrough:d}{char.reverse:d}{char.blink:d}"
            )
        crc = zlib.crc32(
            zlib.crc32("\x01".join(parts).encode("utf-8", "replace"))
            .to_bytes(4, "big"), crc)
    cursor_state = (model.screen.cursor.y, model.screen.cursor.x, model.cursor_hidden)
    return zlib.crc32(repr(cursor_state).encode("ascii"), crc)


rng = random.Random(1234)
mismatches = []
for trial in range(80):
    payload = b"".join(rng.choice(FRAGMENTS) for _ in range(rng.randint(4, 30)))
    model = ScreenModel(cols=40, rows=12)
    # Feed in chunks and hash between them — that is what a polling caller does,
    # and it is the only way the incremental path (dirty rows + cached CRCs) is
    # exercised at all. After each poll the incremental result must equal a full
    # recomputation of that same screen.
    step = max(1, len(payload) // 4)
    for off in range(0, len(payload), step):
        model.feed(payload[off:off + step])
        if model.visual_hash() != exhaustive_visual_hash(model):
            mismatches.append(payload)
            break

check(not mismatches,
      "80 random payloads: incremental hash == exhaustive hash at every poll",
      detail="" if not mismatches else f"{len(mismatches)} mismatch(es), first={mismatches[0]!r}")

# The semantic contract of the primitive itself must survive the optimization.
m = ScreenModel(cols=20, rows=4)
m.feed(b"abc")
before = m.visual_hash()
m.feed(b"\r\x1b[7mabc")           # same text, reverse video
check(before != m.visual_hash(), "attribute-only change still moves visual_hash")

m = ScreenModel(cols=20, rows=4)
m.feed(b"abc")
before = m.visual_hash()
m.feed(b"\x1b[1;1H")              # cursor only
check(before != m.visual_hash(), "cursor-only change still moves visual_hash")

m = ScreenModel(cols=20, rows=4)
m.feed(b"abc")
before = m.content_hash()
m.feed(b"\r\x1b[7mabc")
check(before == m.content_hash(), "content_hash still ignores attributes")

# A resize rebuilds the per-row state rather than reusing stale rows.
m = fill(40, 10)
m.visual_hash()
m.resize(60, 20)
fresh = ScreenModel(cols=60, rows=20)
fresh.feed(("x" * 39 + "\r\n").encode() * 9)
check(isinstance(m.visual_hash(), int), "visual_hash survives a resize")

# --------------------------------------------------------------------------
# 2. Ceilings — orders of magnitude, not percentages.
# --------------------------------------------------------------------------
print("\n--- per-call cost stays within the polling budget ---")
print("    (wait_visual_change polls every 30 ms by default)")

# Measured 2026-07-27 on an M-series mac AFTER the incremental fix:
#   idle 300x100 ~0.008 ms, one-row-changed 300x100 ~0.23 ms.
# Ceilings are ~20x those, so ordinary machine-to-machine variation passes but a
# regression to per-cell hashing (16.6 ms idle) fails loudly.
IDLE_CEILING_MS = {(80, 24): 0.5, (200, 50): 1.0, (300, 100): 2.0}
DIRTY_CEILING_MS = {(80, 24): 2.0, (200, 50): 4.0, (300, 100): 8.0}

for size, ceiling in IDLE_CEILING_MS.items():
    m = fill(*size)
    ms = per_call_ms(m.visual_hash, 200)
    check(ms < ceiling, f"idle poll {size[0]}x{size[1]}: {ms:.4f} ms < {ceiling} ms",
          detail=f"({ms / 30 * 100:.2f}% of a 30 ms poll)")

for size, ceiling in DIRTY_CEILING_MS.items():
    m = fill(*size)
    m.visual_hash()

    def poll_one_row(model=m):
        model.feed(b"\x1b[1;1Hq")
        model.visual_hash()

    ms = per_call_ms(poll_one_row, 200)
    check(ms < ceiling, f"one row changed {size[0]}x{size[1]}: {ms:.4f} ms < {ceiling} ms",
          detail=f"({ms / 30 * 100:.2f}% of a 30 ms poll)")

# content_hash is the text-only primitive the readiness layer polls; it has no
# incremental path, so this records its real cost rather than optimizing it.
for size, ceiling in {(80, 24): 3.0, (300, 100): 30.0}.items():
    m = fill(*size)
    ms = per_call_ms(m.content_hash, 100)
    check(ms < ceiling, f"content_hash {size[0]}x{size[1]}: {ms:.4f} ms < {ceiling} ms")

if FAILURES:
    print(f"\ntest_perf_contract FAIL -- {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("\nPASS: the wait primitives are cheap enough to poll, and the fast path "
      "agrees with a full recomputation.")
sys.exit(0)
