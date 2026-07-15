#!/usr/bin/env python3
"""test_cpr_reply.py — device-query auto-answer regression (DSR-CPR / DA).

A program that emits a cursor-position query (``ESC[6n``) or a device-attributes
query (``ESC[c``) and then SYNCHRONOUSLY waits for the reply will stall or fall
back to a degraded mode if nothing answers. pyte generates the correct reply
(from its own cursor/attr state) and routes it to Screen.write_process_input;
SmartCLI now captures that and PtySession.pump() writes it back to the PTY.

This locks that wiring. Pure/in-memory: a fake backend feeds the query bytes and
captures what gets written back — no PTY, no process. Mutation check: if pump()
stops writing the reply (or ScreenModel stops capturing it), the writes-back
assertions fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core import PtySession, ScreenModel  # noqa: E402
from smartcli_core.pty_backend import PtyBackend  # noqa: E402

failures = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    global failures
    if not cond:
        failures += 1
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  -- {detail}" if detail else ""))


class FakeBackend(PtyBackend):
    """A minimal backend: hands out queued bytes on read, captures writes."""

    def __init__(self) -> None:
        self._to_read: list[bytes] = []
        self.written = bytearray()
        self._alive = True

    def queue(self, data: bytes) -> None:
        self._to_read.append(data)

    # PtyBackend interface --------------------------------------------------
    def spawn(self, cmd, cols, rows) -> None:  # noqa: D401
        pass

    def read_nonblocking(self, timeout: float = 0.0) -> bytes:
        return self._to_read.pop(0) if self._to_read else b""

    def write(self, data: bytes) -> None:
        self.written.extend(data)

    def resize(self, cols: int, rows: int) -> None:
        pass

    def is_alive(self) -> bool:
        return self._alive

    def terminate(self) -> None:
        self._alive = False


def test_screenmodel_captures_replies() -> None:
    m = ScreenModel(80, 24)
    # Move cursor to row 3, col 5 (1-based), then ask for a cursor-position report.
    m.feed(b"\x1b[3;5H\x1b[6n")
    reply = m.drain_replies()
    check(reply == b"\x1b[3;5R", "ScreenModel answers DSR-CPR from its cursor",
          detail=repr(reply))
    # drain is one-shot.
    check(m.drain_replies() == b"", "drain_replies clears after read")
    # Device-attributes query.
    m.feed(b"\x1b[c")
    check(m.drain_replies() == b"\x1b[?6c", "ScreenModel answers DA1")


def test_pump_writes_reply_back() -> None:
    be = FakeBackend()
    sess = PtySession(cols=80, rows=24, backend=be)
    # Program positions the cursor and queries it, all in one read.
    be.queue(b"hello\x1b[2;3H\x1b[6n")
    data = sess.pump()
    check(b"hello" in data, "pump returns the screen bytes it read")
    check(be.written == b"\x1b[2;3R", "pump wrote the CPR reply back to the PTY",
          detail=repr(bytes(be.written)))


def test_no_query_no_write() -> None:
    be = FakeBackend()
    sess = PtySession(cols=80, rows=24, backend=be)
    be.queue(b"just some text, no queries")
    sess.pump()
    check(be.written == b"", "no device query -> nothing written back",
          detail=repr(bytes(be.written)))


def test_reply_survives_resize() -> None:
    # pyte.Screen.resize is in-place (doesn't rebuild the screen or reset
    # write_process_input), so the reply binding must survive a resize.
    m = ScreenModel(80, 24)
    m.resize(100, 30)
    m.feed(b"\x1b[2;2H\x1b[6n")
    check(m.drain_replies() == b"\x1b[2;2R", "CPR still answered after resize")


def test_no_feedback_loop() -> None:
    # Our own replies, fed back in (as an echoing PTY might), must NOT generate a
    # second reply — otherwise a CPR/DA answer could amplify into a loop. The
    # reply terminators (R / ?..c / ..n status) are not queries.
    m = ScreenModel(80, 24)
    m.feed(b"\x1b[3;5R")   # a CPR reply
    m.feed(b"\x1b[?6c")    # a DA reply
    m.feed(b"\x1b[0n")     # a DSR status reply
    check(m.drain_replies() == b"", "replies fed back produce no second reply")


def main() -> int:
    test_screenmodel_captures_replies()
    test_pump_writes_reply_back()
    test_no_query_no_write()
    test_reply_survives_resize()
    test_no_feedback_loop()
    print()
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
