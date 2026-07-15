#!/usr/bin/env python3
"""test_wait_any.py — PtySession.wait_any regression (deterministic).

wait_any is the pexpect expect([...]) analogue: race several regexes and report
WHICH matched first. This locks:
  * the pattern that appears wins and its LIST INDEX is returned,
  * a later-listed pattern wins when only it appears,
  * earliest-in-list wins a same-poll tie (documented ordering),
  * timeout with none matched returns (-1, latest snapshot),
  * min_wait_ms ignores a stale prior match until the guard elapses.

Pure/in-memory: a fake backend feeds bytes on demand. No PTY, no process.
"""
from __future__ import annotations

import sys
import time
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
    """Feeds queued byte chunks one-per-read; optionally delays the first chunk."""

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


def test_first_pattern_matches():
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    be.queue(b">>> ")
    idx, snap = sess.wait_any([r">>> ", r"Traceback"], timeout_ms=2000)
    check(idx == 0, "the prompt pattern matches -> index 0", f"idx={idx}")
    check(">>>" in snap.to_text(), "returned snapshot shows the matched screen")


def test_later_pattern_matches():
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    be.queue(b"Traceback (most recent call last)")
    idx, _ = sess.wait_any([r">>> ", r"Traceback"], timeout_ms=2000)
    check(idx == 1, "only the error pattern is present -> index 1", f"idx={idx}")


def test_earliest_in_list_wins_tie():
    # One screen that matches BOTH patterns; the earlier list entry must win.
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    be.queue(b"ERROR: boom")
    idx, _ = sess.wait_any([r"ERROR", r"boom"], timeout_ms=2000)
    check(idx == 0, "same-poll tie: earliest-in-list pattern wins", f"idx={idx}")
    # And the reverse order proves it's list-order, not text-position.
    be2 = FakeBackend()
    sess2 = PtySession(cols=40, rows=10, backend=be2)
    be2.queue(b"ERROR: boom")
    idx2, _ = sess2.wait_any([r"boom", r"ERROR"], timeout_ms=2000)
    check(idx2 == 0, "reversed list -> the now-first pattern ('boom') wins", f"idx={idx2}")


def test_empty_patterns_short_circuits():
    # An empty list can never match: return (-1, snapshot) immediately instead of
    # spinning the whole timeout window (adversarial-review polish).
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    t0 = time.monotonic()
    idx, snap = sess.wait_any([], timeout_ms=3000)
    elapsed_ms = (time.monotonic() - t0) * 1000
    check(idx == -1, "empty patterns -> index -1", f"idx={idx}")
    check(snap is not None, "empty patterns still returns a snapshot")
    check(elapsed_ms < 500, "empty patterns returns immediately, not after timeout",
          f"elapsed={elapsed_ms:.0f}ms")


def test_timeout_returns_minus_one():
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    # nothing queued -> screen stays blank -> no pattern ever matches
    idx, snap = sess.wait_any([r"never", r"appears"], timeout_ms=250)
    check(idx == -1, "no pattern within the window -> index -1 (timeout)", f"idx={idx}")
    check(snap is not None, "timeout still returns the latest snapshot")


def test_min_wait_ignores_stale_match():
    # The target text is already on screen at call time; min_wait_ms must make
    # wait_any ignore it until the guard elapses, then it still returns the match.
    be = FakeBackend()
    sess = PtySession(cols=40, rows=10, backend=be)
    be.queue(b"$ ")
    sess.pump()  # paint "$ " BEFORE the wait, so it's a stale prior match
    t0 = time.monotonic()
    idx, _ = sess.wait_any([r"\$ "], timeout_ms=2000, min_wait_ms=150)
    elapsed_ms = (time.monotonic() - t0) * 1000
    check(idx == 0, "stale match is still returned after the guard", f"idx={idx}")
    check(elapsed_ms >= 140, "min_wait_ms delayed the match past the guard",
          f"elapsed={elapsed_ms:.0f}ms")


def main():
    for fn in (test_first_pattern_matches, test_later_pattern_matches,
               test_earliest_in_list_wins_tie, test_empty_patterns_short_circuits,
               test_timeout_returns_minus_one, test_min_wait_ignores_stale_match):
        fn()
    print("-" * 60)
    if failures:
        print(f"test_wait_any FAIL -- {failures} check(s) failed")
        return 1
    print("test_wait_any PASS -- all wait_any paths locked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
