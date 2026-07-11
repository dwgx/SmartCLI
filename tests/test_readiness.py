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
        self.last_sleep = None   # duration of the most recent sleep() (seconds)

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        # Advance virtual time; also nudge forward on zero-sleep to guarantee
        # progress so no loop can spin forever in a test.
        self.last_sleep = seconds
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
    """A late flush delivered ONLY on the post-grace `tail = read_fn()` drain must
    resume the wait — not let it return True on the half-drawn (pre-flush) screen.

    This targets readiness.py lines 87-93 specifically. The flush is delivered on
    the exact read that immediately follows a `grace` sleep (grace=40ms, distinct
    from the 30ms poll sleep), so it can only land on the tail drain — the branch
    the earlier version of this test never exercised (mutation-proven false-green).

    Proof of resume: (a) the flush was delivered on a tail drain, and (b) the wait
    kept polling AFTER the flush (reads continued) instead of returning immediately.
    Under a mutant that drops the resume branch, the function returns True right
    after the flush drain → no further reads → this test FAILS.
    """
    clk = _install_clock()
    reads = {"n": 0}
    tail_flush = {"delivered_at": None}
    reads_after_flush = {"n": 0}

    def read_fn():
        reads["n"] += 1
        if tail_flush["delivered_at"] is not None:
            reads_after_flush["n"] += 1
            return b""  # quiet again so it can finally re-settle
        # The tail drain is the read whose immediately-preceding sleep was `grace`
        # (40ms), not a `poll` (30ms). Deliver the flush there, exactly once.
        if clk.last_sleep is not None and abs(clk.last_sleep - 0.040) < 1e-9:
            tail_flush["delivered_at"] = reads["n"]
            return b"late output"
        return b""

    def hash_fn():
        # constant until the flush lands (so quiet accumulates and we reach the
        # tail drain), then a new value that itself settles.
        return 2 if tail_flush["delivered_at"] is not None else 1

    ok = readiness.wait_until_stable(
        read_fn=read_fn,
        get_screen_hash_fn=hash_fn,
        quiet_ms=60, poll_ms=30, max_wait_ms=5000, grace_ms=40, min_wait_ms=0,
    )
    check(ok is True, "wait_until_stable: resumes after tail-drain flush then settles", f"ret={ok}")
    check(tail_flush["delivered_at"] is not None,
          "wait_until_stable: flush landed on the post-grace tail drain",
          f"at read #{tail_flush['delivered_at']}")
    # The crux: after the tail-drain flush, the loop must have RESUMED (more reads),
    # not returned. A mutant dropping the resume branch returns immediately → 0.
    check(reads_after_flush["n"] > 0,
          "wait_until_stable: kept polling after the tail-drain flush (resumed, not returned)",
          f"reads_after_flush={reads_after_flush['n']}")


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


def test_wait_ready_stable_timing_floor():
    """wait_ready must NOT declare STABLE before quiet_ms + min_wait_ms elapse.

    Mirrors test_min_wait_guard but for wait_ready's stability branch. Asserts a
    virtual-time floor, so a mutant that declares STABLE on the first quiet poll
    (ignoring quiet_ms/min_wait_ms) is caught (the false-green M7 gap).
    """
    clk = _install_clock()
    reason, _ = readiness.wait_ready(
        read_fn=seq_reader([]),               # instantly quiet
        get_screen_hash_fn=seq_hashes([5]),   # constant hash
        get_text_fn=seq_text(["idle"]),
        get_snapshot_fn=lambda: "S",
        marker=None, quiet_ms=200, poll_ms=30, max_wait_ms=8000,
        min_wait_ms=300, grace_ms=0,
    )
    check(reason == "STABLE", "wait_ready: eventually STABLE past the floor", f"reason={reason}")
    # Must have waited at least min_wait (0.3s); a no-quiet mutant returns near t=0.
    check(clk.t >= 0.3, "wait_ready: honored quiet_ms + min_wait_ms floor before STABLE",
          f"virt_t={clk.t:.3f}s (>=0.3)")


def test_blank_gate_refuses_stable_on_never_painted_screen():
    """With blank_hash set, a never-painted blank screen must NOT declare STABLE.

    Regression lock for core bug #1: the readiness gate. read_fn never yields
    bytes and the hash stays at the blank baseline → stability is withheld →
    TIMEOUT, not a false STABLE on a screen the program hasn't drawn yet.
    """
    BLANK = 1000
    # wait_until_stable form
    clk = _install_clock()
    ok = readiness.wait_until_stable(
        read_fn=seq_reader([]), get_screen_hash_fn=seq_hashes([BLANK]),
        quiet_ms=200, poll_ms=30, max_wait_ms=1000, grace_ms=40, min_wait_ms=50,
        blank_hash=BLANK,
    )
    check(ok is False, "wait_until_stable: blank_hash gate withholds stable on blank screen", f"ret={ok}")
    # wait_ready form
    _install_clock()
    reason, _ = readiness.wait_ready(
        read_fn=seq_reader([]), get_screen_hash_fn=seq_hashes([BLANK]),
        get_text_fn=seq_text([""]), get_snapshot_fn=lambda: "B",
        marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=1000,
        min_wait_ms=50, grace_ms=40, blank_hash=BLANK,
    )
    check(reason == "TIMEOUT", "wait_ready: blank_hash gate → TIMEOUT not false STABLE", f"reason={reason}")


def test_blank_gate_does_not_harm_drawn_static_screen():
    """The gate must NOT harm a legitimately-drawn, static screen (hash != blank).

    Regression lock: the naive first attempt broke this exact case. A drawn UI
    whose hash differs from the blank baseline and then holds steady must still
    settle to STABLE even with blank_hash supplied.
    """
    _install_clock()
    reason, _ = readiness.wait_ready(
        read_fn=seq_reader([]), get_screen_hash_fn=seq_hashes([5555]),  # != blank
        get_text_fn=seq_text(["drawn UI"]), get_snapshot_fn=lambda: "S",
        marker=None, quiet_ms=100, poll_ms=30, max_wait_ms=5000,
        min_wait_ms=0, grace_ms=0, blank_hash=1000,
    )
    check(reason == "STABLE", "wait_ready: drawn static screen still settles under gate", f"reason={reason}")
    # And once output has been seen, a return to the blank hash still settles.
    _install_clock()
    reads = iter([b"data", b"", b"", b"", b"", b"", b""])
    reason2, _ = readiness.wait_ready(
        read_fn=lambda: next(reads, b""), get_screen_hash_fn=seq_hashes([1000]),
        get_text_fn=seq_text([""]), get_snapshot_fn=lambda: "S",
        marker=None, quiet_ms=100, poll_ms=30, max_wait_ms=5000,
        min_wait_ms=0, grace_ms=0, blank_hash=1000,
    )
    check(reason2 == "STABLE", "wait_ready: seen_any overrides blank gate", f"reason={reason2}")


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
        test_wait_ready_stable, test_wait_ready_stable_timing_floor,
        test_blank_gate_refuses_stable_on_never_painted_screen,
        test_blank_gate_does_not_harm_drawn_static_screen,
        test_wait_ready_timeout,
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

