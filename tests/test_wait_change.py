#!/usr/bin/env python3
"""test_wait_change.py — PtySession.wait_change regression (deterministic).

wait_change is the precise "did my action land?" primitive: block until the
screen content hash changes away from a baseline. This locks:
  * baseline is the screen NOW, without draining pending bytes first (so the
    awaited output can't be folded into the baseline and missed),
  * a real content change returns (True, snapshot),
  * no change within the window returns (False, latest snapshot),
  * an explicit baseline_hash lets a caller wait for change from a known state.

Pure/in-memory: a fake backend feeds bytes on demand. No PTY, no process.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core import PtySession  # noqa: E402
from smartcli_core.pty_backend import PtyBackend  # noqa: E402

failures = 0


def check(cond, label, detail=""):
    global failures
    if not cond:
        failures += 1
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  -- {detail}" if detail else ""))


class FakeBackend(PtyBackend):
    def __init__(self):
        self._q = []
        self._alive = True

    def queue(self, data):
        self._q.append(data)

    def spawn(self, cmd, cols, rows):
        pass

    def read_nonblocking(self, timeout=0.0):
        return self._q.pop(0) if self._q else b""

    def write(self, data):
        pass

    def resize(self, cols, rows):
        pass

    def is_alive(self):
        return self._alive

    def terminate(self):
        self._alive = False


def test_change_detected():
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    be.queue(b"hello world")
    changed, snap = sess.wait_change(timeout_ms=2000)
    check(changed is True, "content change is detected")
    check("hello" in snap.to_text(), "returned snapshot shows the new content")


def test_no_change_times_out():
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    changed, snap = sess.wait_change(timeout_ms=250)
    check(changed is False, "no change within the window -> False (timeout)")
    check(snap is not None, "timeout still returns the latest snapshot")


def test_baseline_not_polluted():
    # The bug this guards: if wait_change drained pending bytes to form the
    # baseline, the awaited output would be in the baseline and never seen.
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    be.queue(b"the output I am waiting for")   # already queued before the call
    changed, _ = sess.wait_change(timeout_ms=2000)
    check(changed is True, "pending bytes at call time still count as a change")


def test_explicit_baseline():
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    be.queue(b"first")
    sess.wait_change(timeout_ms=2000)          # consume 'first'
    h = sess.model.content_hash()
    be.queue(b"\x1b[2J\x1b[Hsecond")           # clear + new
    changed, snap = sess.wait_change(baseline_hash=h, timeout_ms=2000)
    check(changed is True, "explicit baseline_hash detects change from a known state")
    check("second" in snap.to_text(), "snapshot reflects the change")


def main():
    test_change_detected()
    test_no_change_times_out()
    test_baseline_not_polluted()
    test_explicit_baseline()
    print()
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
