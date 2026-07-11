#!/usr/bin/env python
"""test_readiness.py — deterministic unit tests for smartcli_core.readiness.

These cover the failure/edge paths that historically broke and are otherwise only
reachable through flaky real-PTY timing:
  * TIMEOUT   — a screen that never settles / a marker that never matches.
  * STABLE    — the content hash repeats long enough to declare stability.
  * MARKER    — an expected regex is found (beats stability).
  * late-flush — data arrives after the grace sleep → the wait resumes instead of
                 declaring done on a half-drawn screen (the ConPTY quiet-gap bug).
  * min_wait  — stability/marker is NOT declared before the minimum elapsed time.

Determinism: we monkeypatch ``readiness.time.monotonic`` / ``readiness.time.sleep``
with a virtual clock so ``sleep(x)`` advances virtual time by ``x`` and timeouts
fire instantly with no real waiting. This patches only the clock BOUNDARY — the
real decision logic in readiness.py runs unchanged (HARD-LESSONS rule 5: a test
double for the clock/IO edge, never a patch that hides a bug).

Run:  python tests/test_readiness.py     (exit 0 = pass, 1 = fail)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Portable: make the repo root importable regardless of cwd.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from smartcli_core import readiness  # noqa: E402


class VirtualClock:
    """A fake monotonic clock: sleep() advances virtual time; no real waiting."""

    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        # Advance virtual time; also nudge forward on zero-sleep to guarantee
        # progress so no loop can spin forever in a test.
        self.t += seconds if seconds > 0 else 0.001


def _install_clock():
    clk = VirtualClock()
    readiness.time.monotonic = clk.monotonic  # type: ignore[assignment]
    readiness.time.sleep = clk.sleep          # type: ignore[assignment]
    return clk


# scripted-callable helpers ------------------------------------------------

def seq_reader(batches):
    """read_fn that returns each batch in turn, then b'' forever."""
    it = iter(batches)

    def _read():
        return next(it, b"")

    return _read


def seq_hashes(values):
    """hash_fn that returns each value in turn, then repeats the last forever."""
    state = {"i": 0, "vals": list(values)}

    def _hash():
        i = state["i"]
        vals = state["vals"]
        v = vals[i] if i < len(vals) else vals[-1]
        if i < len(vals) - 1:
            state["i"] = i + 1
        return v

    return _hash


def seq_text(values):
    """text_fn that returns each value in turn, then repeats the last forever."""
    state = {"i": 0, "vals": list(values)}

    def _text():
        i = state["i"]
        vals = state["vals"]
        v = vals[i] if i < len(vals) else vals[-1]
        if i < len(vals) - 1:
            state["i"] = i + 1
        return v

    return _text


_fails = []


def check(cond, name, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {name}  {detail}")
    if not cond:
        _fails.append(name)


def test_stable_reached():
    """Hash unchanged + no new bytes for quiet_ms → wait_until_stable True, fast."""
    _install_clock()
    ok = readiness.wait_until_stable(
        read_fn=seq_reader([]),                 # no bytes ever
        get_screen_hash_fn=seq_hashes([42]),    # constant hash
        quiet_ms=200, poll_ms=30, max_wait_ms=8000, grace_ms=0, min_wait_ms=0,
    )
    check(ok is True, "wait_until_stable: constant screen settles", f"ret={ok}")


def test_stable_timeout():
    """Hash never stops changing → returns False (TIMEOUT) within budget, no hang."""
    clk = _install_clock()
    # hash flips forever: 0,1,0,1,... → never quiet
    flip = {"n": 0}

    def churn_hash():
        flip["n"] ^= 1
        return flip["n"]

    ok = readiness.wait_until_stable(
        read_fn=seq_reader([]),
        get_screen_hash_fn=churn_hash,
        quiet_ms=200, poll_ms=30, max_wait_ms=1000, grace_ms=0, min_wait_ms=0,
    )
    check(ok is False, "wait_until_stable: churning screen hits TIMEOUT", f"ret={ok}")
    check(clk.t >= 1.0, "wait_until_stable: respected max_wait ceiling", f"virt_t={clk.t:.2f}s")


def test_late_flush_resume():
    """A late flush after grace resumes the wait instead of declaring done early.

    We inject exactly one late batch on the post-grace `tail = read_fn()` drain.
    readiness must consume it, reset stability, and only return True once the
    screen re-settles — never return on the half-drawn (pre-flush) screen.
    """
    _install_clock()
    reads = {"n": 0}
    flush_at = {"call": None}   # records which read_fn call delivered the flush

    def read_fn():
        reads["n"] += 1
        # Deliver the late flush the first time we've gone quiet long enough that
        # a grace-drain read happens (n>=4 in this cadence), exactly once.
        if flush_at["call"] is None and reads["n"] >= 4:
            flush_at["call"] = reads["n"]
            return b"late output"
        return b""

    def hash_fn():
        # screen changes once the flush has been delivered, then settles at 2
        return 2 if flush_at["call"] is not None else 1

    ok = readiness.wait_until_stable(
        read_fn=read_fn,
        get_screen_hash_fn=hash_fn,
        quiet_ms=60, poll_ms=30, max_wait_ms=5000, grace_ms=40, min_wait_ms=0,
    )
    # Main contract: it re-settled to True AFTER a late flush was consumed.
    check(ok is True, "wait_until_stable: resumes after late flush then settles", f"ret={ok}")
    # A late flush was actually delivered and consumed, and reads continued
    # past that point (so it did NOT return on the stale pre-flush screen).
    check(flush_at["call"] is not None, "wait_until_stable: late flush was delivered", f"flush_at={flush_at['call']}")
    check(reads["n"] > flush_at["call"], "wait_until_stable: kept reading past the late flush",
          f"reads={reads['n']} flush_at={flush_at['call']}")


def test_min_wait_guard():
    """Stability must NOT be declared before min_wait_ms even if screen is quiet."""
    clk = _install_clock()
    ok = readiness.wait_until_stable(
        read_fn=seq_reader([]),
        get_screen_hash_fn=seq_hashes([7]),     # instantly "quiet"
        quiet_ms=50, poll_ms=30, max_wait_ms=8000, grace_ms=0, min_wait_ms=500,
    )
    check(ok is True, "wait_until_stable: settles after min_wait", f"ret={ok}")
    check(clk.t >= 0.5, "wait_until_stable: honored min_wait_ms floor", f"virt_t={clk.t:.3f}s (>=0.5)")


def test_regex_match():
    """wait_for_regex finds the marker and returns (True, snapshot)."""
    _install_clock()
    matched, snap = readiness.wait_for_regex(
        read_fn=seq_reader([b">>> "]),
        get_text_fn=seq_text(["loading...", "loading...", ">>> ready"]),
        get_snapshot_fn=lambda: "SNAP",
        pattern=r">>> ", timeout_ms=5000, poll_ms=30, min_wait_ms=0,
    )
    check(matched is True, "wait_for_regex: finds marker", f"matched={matched}")
    check(snap == "SNAP", "wait_for_regex: returns snapshot on match", f"snap={snap}")


def test_regex_timeout_returns_snapshot():
    """wait_for_regex on a never-matching pattern returns (False, snapshot)."""
    clk = _install_clock()
    matched, snap = readiness.wait_for_regex(
        read_fn=seq_reader([]),
        get_text_fn=seq_text(["nothing here"]),
        get_snapshot_fn=lambda: "LAST",
        pattern=r"WILL_NEVER_APPEAR", timeout_ms=800, poll_ms=30, min_wait_ms=0,
    )
    check(matched is False, "wait_for_regex: TIMEOUT when no match", f"matched={matched}")
    check(snap == "LAST", "wait_for_regex: still returns last snapshot on timeout", f"snap={snap}")
    check(clk.t >= 0.8, "wait_for_regex: respected timeout ceiling", f"virt_t={clk.t:.2f}s")


def test_regex_min_wait():
    """A match present from t=0 must be ignored until min_wait_ms elapses."""
    clk = _install_clock()
    matched, _ = readiness.wait_for_regex(
        read_fn=seq_reader([]),
        get_text_fn=seq_text([">>> "]),          # matches immediately
        get_snapshot_fn=lambda: None,
        pattern=r">>> ", timeout_ms=5000, poll_ms=30, min_wait_ms=300,
    )
    check(matched is True, "wait_for_regex: eventually matches past min_wait", f"matched={matched}")
    check(clk.t >= 0.3, "wait_for_regex: did not match before min_wait", f"virt_t={clk.t:.3f}s (>=0.3)")


def test_wait_ready_marker_beats_stability():
    """wait_ready returns MARKER when the regex hits (even amid churn)."""
    _install_clock()
    # screen keeps changing (never stable) but marker appears on 3rd text sample
    reason, snap = readiness.wait_ready(
        read_fn=seq_reader([b"a", b"b", b"c"]),
        get_screen_hash_fn=seq_hashes([1, 2, 3, 4, 5]),   # churning
        get_text_fn=seq_text(["...", "...", "DONE!"]),
        get_snapshot_fn=lambda: "S",
        marker=r"DONE!", quiet_ms=200, poll_ms=30, max_wait_ms=5000, min_wait_ms=0,
    )
    check(reason == "MARKER", "wait_ready: marker beats a churning screen", f"reason={reason}")


def test_wait_ready_stable():
    """wait_ready returns STABLE when no marker and screen settles."""
    _install_clock()
    reason, _ = readiness.wait_ready(
        read_fn=seq_reader([]),
        get_screen_hash_fn=seq_hashes([9]),
        get_text_fn=seq_text(["idle"]),
        get_snapshot_fn=lambda: "S",
        marker=None, quiet_ms=100, poll_ms=30, max_wait_ms=5000, min_wait_ms=0, grace_ms=0,
    )
    check(reason == "STABLE", "wait_ready: settles to STABLE with no marker", f"reason={reason}")


def test_wait_ready_timeout():
    """wait_ready returns TIMEOUT when marker never matches and screen churns."""
    clk = _install_clock()
    flip = {"n": 0}

    def churn_hash():
        flip["n"] ^= 1
        return flip["n"]

    reason, snap = readiness.wait_ready(
        read_fn=seq_reader([b"x", b"y", b"z"] * 100),   # bytes keep coming
        get_screen_hash_fn=churn_hash,
        get_text_fn=seq_text(["busy"]),
        get_snapshot_fn=lambda: "LASTSNAP",
        marker=r"NOPE", quiet_ms=200, poll_ms=30, max_wait_ms=1000, min_wait_ms=0,
    )
    check(reason == "TIMEOUT", "wait_ready: TIMEOUT when nothing satisfies", f"reason={reason}")
    check(snap == "LASTSNAP", "wait_ready: returns last snapshot on timeout", f"snap={snap}")
    check(clk.t >= 1.0, "wait_ready: respected max_wait ceiling", f"virt_t={clk.t:.2f}s")


def main() -> int:
    import time as _real_time
    t0 = _real_time.perf_counter()
    print("=" * 60)
    print("readiness deterministic unit tests (virtual clock, no real waits)")
    print("=" * 60)
    for fn in (
        test_stable_reached, test_stable_timeout, test_late_flush_resume,
        test_min_wait_guard, test_regex_match, test_regex_timeout_returns_snapshot,
        test_regex_min_wait, test_wait_ready_marker_beats_stability,
        test_wait_ready_stable, test_wait_ready_timeout,
    ):
        fn()
    wall = _real_time.perf_counter() - t0
    print("-" * 60)
    if _fails:
        print(f"FAIL: {len(_fails)} check(s) failed: {_fails}")
        return 1
    print(f"PASS: all readiness edge paths covered in {wall*1000:.0f} ms wall (deterministic)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

