#!/usr/bin/env python3
"""test_child_death_wait.py — a dead child is a wait OUTCOME, not a long timeout.

Every wait primitive used to be a pure deadline loop: if the program under test
crashed on your first input, a 30s `wait_ready` sat there for the full 30s
reporting TIMEOUT — advice that is not merely slow but wrong, because TIMEOUT
means "still running, send again later". pexpect's `EOF` sentinel and
Microsoft's `session_stopped()` both make child death a first-class result;
this gate locks that ours does too, for all four readiness primitives plus the
two session-level hash-change waits.

Covered here:
  * the child dies mid-wait → the wait returns the EXITED outcome PROMPTLY
    (asserted in virtual time, so "promptly" is a number, not a vibe),
  * the child stays alive → the wait still times out normally,
  * with NO predicate the behaviour is the old one (a dead child yields the
    ordinary timeout, i.e. the default path is genuinely untouched),
  * the race: a marker that becomes visible on the same poll the child dies on
    is reported as MARKER; only "died before anything matched" is EXITED,
  * the sentinel is a distinct value: falsy, `!= -1`, `!= False`, `repr`
    "EXITED", identity-comparable, hashable,
  * the exit check runs BEFORE the deadline check (a dead child at the ceiling
    is EXITED, not TIMEOUT),
  * `PtySession` threads it with no ceremony: `detect_child_exit = True`, or a
    per-call `alive_fn=` that overrides the session default.

Pure/in-memory: scripted callables plus a fake backend. No PTY, no child
process, and a virtual clock for every readiness-level case — nothing here
sleeps for real.
"""
from __future__ import annotations

import sys
import time as _real_time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core import PtySession  # noqa: E402
from smartcli_core import readiness  # noqa: E402
from smartcli_core.pty_backend import PtyBackend  # noqa: E402

_fails: list[str] = []


def check(cond, name, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {name}  {detail}")
    if not cond:
        _fails.append(name)


# -- virtual clock --------------------------------------------------------
# Same trick as test_readiness.py: readiness calls `time.monotonic()`/`sleep()`,
# so replacing them on the `time` module it imported makes every loop advance
# virtual time instead of really waiting. Installed only around the
# readiness-level tests so the session-level wall-clock measurements below are
# real.

class VirtualClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.last_sleep = None

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.last_sleep = seconds
        self.t += seconds if seconds > 0 else 0.001


class clock_installed:
    """Context manager: virtual time inside, real time restored outside."""

    def __enter__(self) -> VirtualClock:
        self.clk = VirtualClock()
        self._real_monotonic = _real_time.monotonic
        self._real_sleep = _real_time.sleep
        _real_time.monotonic = self.clk.monotonic
        _real_time.sleep = self.clk.sleep
        return self.clk

    def __exit__(self, *exc) -> None:
        _real_time.monotonic = self._real_monotonic
        _real_time.sleep = self._real_sleep


# -- scripted callables ---------------------------------------------------

def churning_hash():
    """hash_fn that differs on every call: the screen never settles."""
    state = {"n": 0}

    def _hash():
        state["n"] += 1
        return state["n"]

    return _hash


def constant_hash():
    return lambda: 12345


def dies_after(n):
    """alive_fn: True for the first ``n`` polls, False from poll n+1 on."""
    state = {"calls": 0}

    def _alive():
        state["calls"] += 1
        return state["calls"] <= n

    _alive.calls = state          # type: ignore[attr-defined]
    return _alive


def always_alive():
    def _alive():
        return True

    _alive.calls = {"n": 0}       # type: ignore[attr-defined]
    return _alive


class FakeScreen:
    """A text buffer whose content hash changes on every feed."""

    def __init__(self) -> None:
        self.buf = ""
        self.h = 0

    def feed(self, data):
        self.buf += data.decode("utf-8", "replace")
        self.h += 1

    def text(self):
        return self.buf

    def hash(self):
        return self.h

    def snapshot(self):
        return f"SNAP:{self.buf!r}"


def reader_for(screen, batches):
    """read_fn feeding ``batches`` in order into ``screen``, then b'' forever."""
    it = iter(batches)

    def _read():
        data = next(it, b"")
        if data:
            screen.feed(data)
        return data

    return _read


def noop_reader():
    return lambda: b""


# =========================================================================
# readiness.wait_until_stable
# =========================================================================

def test_stable_child_dies_returns_exited_promptly():
    """The screen never settles AND the child dies → EXITED, long before the ceiling."""
    with clock_installed() as clk:
        res = readiness.wait_until_stable(
            read_fn=noop_reader(),
            get_screen_hash_fn=churning_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=40,
            alive_fn=dies_after(5),
        )
    check(res is readiness.EXITED, "wait_until_stable: dead child → EXITED", f"res={res!r}")
    check(clk.t < 1.0, "wait_until_stable: returned promptly, not at the 30s ceiling",
          f"virt_t={clk.t:.3f}s (ceiling was 30s)")


def test_stable_child_alive_still_times_out():
    """Same churn, child alive throughout → the ordinary False timeout, at the ceiling."""
    with clock_installed() as clk:
        res = readiness.wait_until_stable(
            read_fn=noop_reader(),
            get_screen_hash_fn=churning_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=40,
            alive_fn=always_alive(),
        )
    check(res is False, "wait_until_stable: live child, no settle → False (timeout)", f"res={res!r}")
    check(clk.t >= 30.0, "wait_until_stable: a live child still runs to the ceiling",
          f"virt_t={clk.t:.2f}s")


def test_stable_default_path_ignores_death_entirely():
    """THE REGRESSION NET: with no predicate, a dead child is NOT observable."""
    with clock_installed() as clk:
        res = readiness.wait_until_stable(
            read_fn=noop_reader(),
            get_screen_hash_fn=churning_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=40,
            # NOTE: no alive_fn. This is exactly the pre-change call.
        )
    check(res is False, "wait_until_stable: no predicate → plain False, as before", f"res={res!r}")
    check(res is not readiness.EXITED, "wait_until_stable: no predicate can never yield EXITED")
    check(clk.t >= 30.0, "wait_until_stable: no predicate sits out the whole ceiling",
          f"virt_t={clk.t:.2f}s")


def test_stable_content_wins_over_death():
    """The race, other direction: settle on the poll the child dies → True."""
    # Constant hash + quiet_ms=0 makes the stability branch fire on poll 3, so a
    # predicate that dies on its 3rd call is asked exactly once more than the
    # polls before it, and the settle still wins because content is checked
    # first. Dies on call 2 instead and the same scenario yields EXITED — that
    # pairing is the point: order is observable, not incidental.
    with clock_installed():
        won = readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=0, poll_ms=30, max_wait_ms=30000, grace_ms=0,
            alive_fn=dies_after(2),
        )
        lost = readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=0, poll_ms=30, max_wait_ms=30000, grace_ms=0,
            alive_fn=dies_after(1),
        )
    check(won is True, "wait_until_stable: settle on the death poll wins (True)", f"res={won!r}")
    check(lost is readiness.EXITED,
          "wait_until_stable: death one poll earlier → EXITED (ordering is real)", f"res={lost!r}")


# =========================================================================
# readiness.wait_for_regex
# =========================================================================

def test_regex_child_dies_returns_exited_promptly():
    with clock_installed() as clk:
        matched, snap = readiness.wait_for_regex(
            read_fn=noop_reader(), get_text_fn=lambda: "nothing to see",
            get_snapshot_fn=lambda: "SNAP", pattern=r">>> ",
            timeout_ms=30000, poll_ms=30, alive_fn=dies_after(3),
        )
    check(matched is readiness.EXITED, "wait_for_regex: dead child → EXITED", f"matched={matched!r}")
    check(snap == "SNAP", "wait_for_regex: EXITED still returns the last snapshot")
    check(clk.t < 1.0, "wait_for_regex: returned promptly", f"virt_t={clk.t:.3f}s")


def test_regex_child_alive_still_times_out():
    with clock_installed() as clk:
        matched, _ = readiness.wait_for_regex(
            read_fn=noop_reader(), get_text_fn=lambda: "nothing to see",
            get_snapshot_fn=lambda: "SNAP", pattern=r">>> ",
            timeout_ms=30000, poll_ms=30, alive_fn=always_alive(),
        )
    check(matched is False, "wait_for_regex: live child, no match → False", f"matched={matched!r}")
    check(clk.t >= 30.0, "wait_for_regex: a live child still runs to the ceiling",
          f"virt_t={clk.t:.2f}s")


def test_regex_default_path_unchanged():
    with clock_installed() as clk:
        matched, snap = readiness.wait_for_regex(
            read_fn=noop_reader(), get_text_fn=lambda: "nothing to see",
            get_snapshot_fn=lambda: "SNAP", pattern=r">>> ", timeout_ms=30000, poll_ms=30,
        )
    check(matched is False, "wait_for_regex: no predicate → plain False", f"matched={matched!r}")
    check(matched is not readiness.EXITED, "wait_for_regex: no predicate never yields EXITED")
    check(snap == "SNAP", "wait_for_regex: no predicate still returns a snapshot")
    check(clk.t >= 30.0, "wait_for_regex: no predicate sits out the whole ceiling",
          f"virt_t={clk.t:.2f}s")


def test_regex_match_still_beats_death():
    """A live marker is reported as a match even with a predicate that says dead."""
    screen = FakeScreen()
    alive = dies_after(0)          # dead from the very first poll
    matched, snap = readiness.wait_for_regex(
        read_fn=reader_for(screen, [b">>> "]),
        get_text_fn=screen.text, get_snapshot_fn=screen.snapshot,
        pattern=r">>> ", timeout_ms=30000, poll_ms=30, min_wait_ms=0,
        alive_fn=alive,
    )
    check(matched is True, "wait_for_regex: marker on the death poll is still a match",
          f"matched={matched!r}")
    check(">>>" in snap, "wait_for_regex: that match carries the screen the agent asked for")
    check(alive.calls["calls"] == 0,
          "wait_for_regex: predicate is not even asked once the match fires",
          f"calls={alive.calls['calls']}")


# =========================================================================
# readiness.wait_any
# =========================================================================

def test_any_child_dies_returns_exited_promptly():
    with clock_installed() as clk:
        idx, snap = readiness.wait_any(
            read_fn=noop_reader(), get_text_fn=lambda: "nothing to see",
            get_snapshot_fn=lambda: "SNAP", patterns=[r">>> ", r"Traceback"],
            timeout_ms=30000, poll_ms=30, alive_fn=dies_after(3),
        )
    check(idx is readiness.EXITED, "wait_any: dead child → EXITED", f"idx={idx!r}")
    check(snap == "SNAP", "wait_any: EXITED still returns the last snapshot")
    check(idx != -1, "wait_any: EXITED is not the -1 timeout sentinel")
    check(clk.t < 1.0, "wait_any: returned promptly", f"virt_t={clk.t:.3f}s")


def test_any_child_alive_still_times_out():
    with clock_installed() as clk:
        idx, _ = readiness.wait_any(
            read_fn=noop_reader(), get_text_fn=lambda: "nothing to see",
            get_snapshot_fn=lambda: "SNAP", patterns=[r">>> ", r"Traceback"],
            timeout_ms=30000, poll_ms=30, alive_fn=always_alive(),
        )
    check(idx == -1, "wait_any: live child, no pattern → -1 (timeout)", f"idx={idx}")
    check(clk.t >= 30.0, "wait_any: a live child still runs to the ceiling", f"virt_t={clk.t:.2f}s")


def test_any_default_path_unchanged():
    with clock_installed() as clk:
        idx, snap = readiness.wait_any(
            read_fn=noop_reader(), get_text_fn=lambda: "nothing to see",
            get_snapshot_fn=lambda: "SNAP", patterns=[r">>> "], timeout_ms=30000, poll_ms=30,
        )
    check(idx == -1, "wait_any: no predicate → plain -1", f"idx={idx}")
    check(idx is not readiness.EXITED, "wait_any: no predicate never yields EXITED")
    check(snap == "SNAP", "wait_any: no predicate still returns a snapshot")
    check(clk.t >= 30.0, "wait_any: no predicate sits out the whole ceiling", f"virt_t={clk.t:.2f}s")


def test_any_match_beats_death():
    screen = FakeScreen()
    alive = dies_after(0)
    idx, _ = readiness.wait_any(
        read_fn=reader_for(screen, [b"Traceback (most recent call last)"]),
        get_text_fn=screen.text, get_snapshot_fn=screen.snapshot,
        patterns=[r">>> ", r"Traceback"], timeout_ms=30000, poll_ms=30, min_wait_ms=0,
        alive_fn=alive,
    )
    check(idx == 1, "wait_any: pattern on the death poll still wins", f"idx={idx}")
    check(alive.calls["calls"] == 0, "wait_any: predicate not asked once a pattern matches",
          f"calls={alive.calls['calls']}")


# =========================================================================
# readiness.wait_ready — the MARKER/STABLE/TIMEOUT/EXITED race
# =========================================================================

def test_ready_child_dies_returns_exited_reason():
    with clock_installed() as clk:
        reason, snap = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=churning_hash(),
            get_text_fn=lambda: "", get_snapshot_fn=lambda: "SNAP",
            marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=30000, min_wait_ms=0,
            grace_ms=40, alive_fn=dies_after(4),
        )
    check(reason == readiness.EXITED_REASON, "wait_ready: dead child → EXITED reason",
          f"reason={reason}")
    check(reason != "TIMEOUT", "wait_ready: EXITED cannot be confused with TIMEOUT")
    check(snap == "SNAP", "wait_ready: EXITED still returns the last snapshot")
    check(clk.t < 1.0, "wait_ready: returned promptly", f"virt_t={clk.t:.3f}s")


def test_ready_child_alive_still_times_out():
    with clock_installed() as clk:
        reason, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=churning_hash(),
            get_text_fn=lambda: "", get_snapshot_fn=lambda: "SNAP",
            marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=30000, min_wait_ms=0,
            grace_ms=40, alive_fn=always_alive(),
        )
    check(reason == "TIMEOUT", "wait_ready: live child, nothing satisfied → TIMEOUT", f"reason={reason}")
    check(clk.t >= 30.0, "wait_ready: a live child still runs to the ceiling", f"virt_t={clk.t:.2f}s")


def test_ready_default_path_unchanged():
    with clock_installed() as clk:
        reason, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=churning_hash(),
            get_text_fn=lambda: "", get_snapshot_fn=lambda: "SNAP",
            marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=30000, min_wait_ms=0,
            grace_ms=40,
        )
    check(reason == "TIMEOUT", "wait_ready: no predicate → plain TIMEOUT", f"reason={reason}")
    check(clk.t >= 30.0, "wait_ready: no predicate sits out the whole ceiling", f"virt_t={clk.t:.2f}s")


def test_ready_marker_beats_death_on_the_same_poll():
    """THE RACE, stated as a decision: content first, so MARKER wins."""
    screen = FakeScreen()
    alive = dies_after(0)          # already gone before the first poll
    reason, snap = readiness.wait_ready(
        read_fn=reader_for(screen, [b">>> "]),
        get_screen_hash_fn=screen.hash, get_text_fn=screen.text,
        get_snapshot_fn=screen.snapshot,
        marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=30000, min_wait_ms=0,
        grace_ms=40, alive_fn=alive,
    )
    check(reason == "MARKER",
          "wait_ready RACE: marker printed as the child's last act → MARKER, not EXITED",
          f"reason={reason}")
    check(">>>" in snap, "wait_ready: that MARKER carries the output the agent waited for")
    check(alive.calls["calls"] == 0, "wait_ready: predicate not asked once MARKER fires",
          f"calls={alive.calls['calls']}")


def test_ready_exit_is_checked_before_the_deadline():
    """max_wait_ms=0: the deadline is already spent on poll 1. Death still wins."""
    with clock_installed():
        dead_first, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=churning_hash(),
            get_text_fn=lambda: "", get_snapshot_fn=lambda: "SNAP",
            marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=0, min_wait_ms=0,
            grace_ms=40, alive_fn=lambda: False,
        )
        alive_first, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=churning_hash(),
            get_text_fn=lambda: "", get_snapshot_fn=lambda: "SNAP",
            marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=0, min_wait_ms=0,
            grace_ms=40,
        )
    check(dead_first == readiness.EXITED_REASON,
          "wait_ready: death is decided BEFORE the deadline check", f"reason={dead_first}")
    check(alive_first == "TIMEOUT",
          "wait_ready: same exhausted deadline without a predicate → TIMEOUT", f"reason={alive_first}")


def test_ready_stable_still_works_with_a_predicate():
    """Opting into EXITED must not disturb the ordinary STABLE path."""
    with clock_installed():
        reason, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            get_text_fn=lambda: "", get_snapshot_fn=lambda: "SNAP",
            marker=None, quiet_ms=0, poll_ms=30, max_wait_ms=30000, min_wait_ms=0,
            grace_ms=0, alive_fn=always_alive(),
        )
    check(reason == "STABLE", "wait_ready: live child, quiet screen → STABLE", f"reason={reason}")


# =========================================================================
# The sentinel itself
# =========================================================================

def test_exited_sentinel_is_a_distinct_value():
    E = readiness.EXITED
    check(isinstance(E, readiness.Exited), "EXITED is an Exited instance")
    check(repr(E) == "EXITED", "EXITED reprs as EXITED", f"repr={E!r}")
    check(bool(E) is False, "EXITED is falsy, so `if wait_stable():` still means 'settled'")
    check((E == False) is False, "EXITED == False evaluates to False, not to True")
    check(E != -1, "EXITED is not the wait_any timeout sentinel -1")
    check(E != True, "EXITED is not True")
    check(hash(E) == hash(readiness.EXITED), "EXITED is hashable (usable as a dict key)")
    check(len({E, readiness.EXITED}) == 1, "EXITED collapses to one set/dict entry")


# =========================================================================
# PtySession threading
# =========================================================================

class DyingBackend(PtyBackend):
    """Fake backend whose child reports itself gone after ``die_after`` reads."""

    def __init__(self, die_after=1):
        self._q = []
        self._alive = True
        self._reads = 0
        self._die_after = die_after

    def queue(self, data):
        self._q.append(data)

    def spawn(self, cmd, cols, rows):
        pass

    def read_nonblocking(self, timeout=0.0):
        self._reads += 1
        if self._reads >= self._die_after:
            self._alive = False
        return self._q.pop(0) if self._q else b""

    def write(self, data):
        pass

    def resize(self, cols, rows):
        pass

    def is_alive(self):
        return self._alive

    def terminate(self):
        self._alive = False


def test_session_detect_child_exit_needs_no_argument():
    be = DyingBackend(die_after=1)
    sess = PtySession(cols=40, rows=10, backend=be)
    sess.detect_child_exit = True
    t0 = _real_time.monotonic()
    reason, snap = sess.wait_ready(marker=r">>> ", max_wait_ms=5000, min_wait_ms=0)
    elapsed_ms = (_real_time.monotonic() - t0) * 1000
    check(reason == readiness.EXITED_REASON,
          "PtySession: detect_child_exit=True turns a crash into an EXITED reason", f"reason={reason}")
    check(snap is not None, "PtySession: EXITED still hands back a snapshot")
    check(elapsed_ms < 500, "PtySession: EXITED arrives in one poll, not after the 5s ceiling",
          f"elapsed={elapsed_ms:.0f}ms")


def test_session_default_is_off():
    be = DyingBackend(die_after=1)
    sess = PtySession(cols=40, rows=10, backend=be)
    t0 = _real_time.monotonic()
    reason, _ = sess.wait_ready(marker=r">>> ", max_wait_ms=400, min_wait_ms=0)
    elapsed_ms = (_real_time.monotonic() - t0) * 1000
    check(reason == "TIMEOUT",
          "PtySession: default detect_child_exit=False → unchanged TIMEOUT", f"reason={reason}")
    check(elapsed_ms >= 300, "PtySession: default really does sit out the whole ceiling",
          f"elapsed={elapsed_ms:.0f}ms")


def test_session_per_call_alive_fn_overrides_the_default():
    """An explicit predicate wins over the session flag, in both directions."""
    be = DyingBackend(die_after=1)
    sess = PtySession(cols=40, rows=10, backend=be)
    sess.detect_child_exit = True
    reason, _ = sess.wait_ready(marker=r">>> ", max_wait_ms=400, min_wait_ms=0,
                               alive_fn=lambda: True)
    check(reason == "TIMEOUT",
          "PtySession: per-call alive_fn=True defeats detect_child_exit=True", f"reason={reason}")

    be2 = DyingBackend(die_after=1)
    sess2 = PtySession(cols=40, rows=10, backend=be2)
    reason2, _ = sess2.wait_ready(marker=r">>> ", max_wait_ms=5000, min_wait_ms=0,
                                 alive_fn=be2.is_alive)
    check(reason2 == readiness.EXITED_REASON,
          "PtySession: per-call alive_fn works with the session flag off", f"reason={reason2}")


def test_session_other_waits_also_see_death():
    """wait_stable / wait_for / wait_any / wait_change all report it too."""
    # wait_stable returns a bare value, not a (value, snapshot) pair.
    be = DyingBackend(die_after=2)
    sess = PtySession(cols=40, rows=10, backend=be)
    sess.detect_child_exit = True
    settled = sess.wait_stable(quiet_ms=200, max_wait_ms=5000)
    check(settled is readiness.EXITED,
          "PtySession.wait_stable: a dead child is reported, not waited out",
          f"res={settled!r}")

    for name, call, want in (
        ("wait_for", lambda s: s.wait_for(r">>> ", timeout_ms=5000)[0], readiness.EXITED),
        ("wait_any", lambda s: s.wait_any([r">>> "], timeout_ms=5000)[0], readiness.EXITED),
        ("wait_change", lambda s: s.wait_change(timeout_ms=5000)[0], readiness.EXITED),
        ("wait_visual_change", lambda s: s.wait_visual_change(timeout_ms=5000)[0], readiness.EXITED),
    ):
        be = DyingBackend(die_after=2)
        sess = PtySession(cols=40, rows=10, backend=be)
        sess.detect_child_exit = True
        first = call(sess)
        check(first is want, f"PtySession.{name}: a dead child is reported, not waited out",
              f"res={first!r}")

    # And the default path for each is unchanged (no predicate → old sentinel).
    for name, call, want in (
        ("wait_stable", lambda s: s.wait_stable(quiet_ms=0, max_wait_ms=0, grace_ms=0), False),
        ("wait_for", lambda s: s.wait_for(r">>> ", timeout_ms=0)[0], False),
        ("wait_any", lambda s: s.wait_any([r">>> "], timeout_ms=0)[0], -1),
        ("wait_change", lambda s: s.wait_change(timeout_ms=0)[0], False),
    ):
        be = DyingBackend(die_after=1)
        sess = PtySession(cols=40, rows=10, backend=be)
        first = call(sess)
        check(first == want and first is not readiness.EXITED,
              f"PtySession.{name}: no predicate → the pre-existing result", f"res={first!r}")


def main() -> int:
    t0 = _real_time.perf_counter()
    print("=" * 68)
    print("child-death wait outcomes (virtual clock + fake backend; no real waits)")
    print("=" * 68)
    for fn in (
        test_stable_child_dies_returns_exited_promptly,
        test_stable_child_alive_still_times_out,
        test_stable_default_path_ignores_death_entirely,
        test_stable_content_wins_over_death,
        test_regex_child_dies_returns_exited_promptly,
        test_regex_child_alive_still_times_out,
        test_regex_default_path_unchanged,
        test_regex_match_still_beats_death,
        test_any_child_dies_returns_exited_promptly,
        test_any_child_alive_still_times_out,
        test_any_default_path_unchanged,
        test_any_match_beats_death,
        test_ready_child_dies_returns_exited_reason,
        test_ready_child_alive_still_times_out,
        test_ready_default_path_unchanged,
        test_ready_marker_beats_death_on_the_same_poll,
        test_ready_exit_is_checked_before_the_deadline,
        test_ready_stable_still_works_with_a_predicate,
        test_exited_sentinel_is_a_distinct_value,
        test_session_detect_child_exit_needs_no_argument,
        test_session_default_is_off,
        test_session_per_call_alive_fn_overrides_the_default,
        test_session_other_waits_also_see_death,
    ):
        fn()
    wall = _real_time.perf_counter() - t0
    print("-" * 68)
    if _fails:
        print(f"FAIL: {len(_fails)} check(s) failed: {_fails}")
        return 1
    print(f"PASS: child death is a first-class wait outcome, in {wall*1000:.0f} ms wall")
    return 0


if __name__ == "__main__":
    sys.exit(main())