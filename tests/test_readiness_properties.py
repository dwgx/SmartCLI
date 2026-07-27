#!/usr/bin/env python3
"""test_readiness_properties.py — property-based tests for the wait primitives.

``readiness.py`` is concurrency-timing code: its correctness depends on the
interleaving of byte arrivals, hash changes and clock advances. The existing
``test_readiness.py`` pins specific scenarios, which is the right thing for
regressions but cannot cover the state space — a wait primitive has to hold its
invariants for EVERY arrival pattern, not the dozen someone wrote down.

This file states the invariants as properties and lets Hypothesis search for
counterexamples across arbitrary schedules and parameter combinations. Time is a
virtual clock (``time.monotonic``/``time.sleep`` are patched), so runs are
deterministic, instant, and cannot flake on a loaded machine.

Invariants asserted:
  * wait_until_stable never reports stable before ``min_wait_ms`` has elapsed
  * ...nor while a ``blank_hash`` screen has produced no output (the readiness gate)
  * ...nor before ``quiet_ms`` of genuine quiet, on any arrival schedule
  * ...and it always terminates within ``max_wait_ms`` (+ one grace period)
  * wait_for_regex reports True only when the pattern is really on screen
  * wait_any returns the EARLIEST-in-list index among those matching in a poll,
    -1 on timeout, and never an index outside the input list
  * a wait that returns False leaves the caller able to see the last screen

Skips cleanly (exit 0) when Hypothesis is not installed, so it never blocks a
plain checkout. Pure/in-memory: no PTY, no subprocess.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
except ImportError:
    print("SKIP: hypothesis not installed (pip install hypothesis)")
    raise SystemExit(0)

from smartcli_core import readiness  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FAILURES: list[str] = []


def report(label: str, exc: BaseException | None = None) -> None:
    if exc is None:
        print(f"  [PASS] {label}")
    else:
        FAILURES.append(f"{label}: {exc}")
        print(f"  [FAIL] {label}\n         {exc}")


class VirtualClock:
    """Deterministic stand-in for monotonic time + sleep.

    Patched over the module under test so a "wait" costs no wall-clock time and
    the schedule is exactly what the test says it is.
    """

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


class Feed:
    """A scripted screen: a schedule of (bytes_arriving, hash) per poll."""

    def __init__(self, schedule: list[tuple[int, int]]) -> None:
        self.schedule = list(schedule)
        self.index = 0
        self.hash = 0
        self.reads = 0

    def read(self) -> bytes:
        self.reads += 1
        if self.index < len(self.schedule):
            nbytes, new_hash = self.schedule[self.index]
            self.index += 1
            self.hash = new_hash
            return b"x" * nbytes
        return b""

    def get_hash(self) -> int:
        return self.hash


def run_stable(clock: VirtualClock, feed: Feed, **kwargs) -> tuple[bool, float]:
    start = clock.now
    result = readiness.wait_until_stable(feed.read, feed.get_hash, **kwargs)
    return result, clock.now - start


def patched(fn):
    """Run fn with readiness' time functions swapped for a virtual clock."""
    def wrapper(*args, **kwargs):
        clock = VirtualClock()
        real_time = readiness.time
        class _T:
            monotonic = staticmethod(clock.monotonic)
            sleep = staticmethod(clock.sleep)
        readiness.time = _T  # type: ignore[assignment]
        try:
            return fn(clock, *args, **kwargs)
        finally:
            readiness.time = real_time  # type: ignore[assignment]
    return wrapper


SETTINGS = settings(max_examples=250, deadline=None,
                    suppress_health_check=[HealthCheck.function_scoped_fixture])

# A schedule: each entry is (bytes_this_poll, screen_hash_after).
schedules = st.lists(
    st.tuples(st.integers(min_value=0, max_value=8), st.integers(min_value=0, max_value=3)),
    min_size=0, max_size=25)


# --------------------------------------------------------------------------
print("--- wait_until_stable invariants (any arrival schedule) ---")


@SETTINGS
@given(schedule=schedules, min_wait_ms=st.integers(min_value=0, max_value=900),
       quiet_ms=st.integers(min_value=10, max_value=300))
def prop_min_wait_respected(schedule, min_wait_ms, quiet_ms):
    @patched
    def body(clock):
        feed = Feed(schedule)
        ok, elapsed = run_stable(clock, feed, quiet_ms=quiet_ms, poll_ms=30,
                                 max_wait_ms=5000, grace_ms=0,
                                 min_wait_ms=min_wait_ms)
        if ok:
            # Stability may only be declared once min_wait has really passed.
            assert elapsed >= min_wait_ms / 1000.0 - 1e-9, (
                f"declared stable after {elapsed:.3f}s < min_wait {min_wait_ms}ms")
    body()


@SETTINGS
@given(schedule=schedules, quiet_ms=st.integers(min_value=10, max_value=400))
def prop_quiet_time_respected(schedule, quiet_ms):
    @patched
    def body(clock):
        feed = Feed(schedule)
        ok, elapsed = run_stable(clock, feed, quiet_ms=quiet_ms, poll_ms=30,
                                 max_wait_ms=9000, grace_ms=0, min_wait_ms=0)
        if ok:
            assert elapsed >= quiet_ms / 1000.0 - 1e-9, (
                f"declared stable after {elapsed:.3f}s < quiet {quiet_ms}ms")
    body()


@SETTINGS
@given(schedule=schedules, max_wait_ms=st.integers(min_value=50, max_value=3000),
       grace_ms=st.integers(min_value=0, max_value=100))
def prop_always_terminates(schedule, max_wait_ms, grace_ms):
    @patched
    def body(clock):
        feed = Feed(schedule)
        ok, elapsed = run_stable(clock, feed, quiet_ms=50, poll_ms=30,
                                 max_wait_ms=max_wait_ms, grace_ms=grace_ms,
                                 min_wait_ms=0)
        # A wait must never run away: bounded by max_wait plus the final grace
        # sleep and one poll of slack.
        budget = (max_wait_ms + grace_ms) / 1000.0 + 0.05
        assert elapsed <= budget, f"ran {elapsed:.3f}s over budget {budget:.3f}s"
    body()


@SETTINGS
@given(polls=st.integers(min_value=0, max_value=20),
       quiet_ms=st.integers(min_value=10, max_value=200))
def prop_blank_gate_never_settles(polls, quiet_ms):
    """The readiness gate: a never-painted blank screen must NOT read as stable."""
    @patched
    def body(clock):
        # No bytes ever arrive and the hash stays at the blank baseline.
        feed = Feed([(0, 7)] * polls)
        feed.hash = 7
        ok, _ = run_stable(clock, feed, quiet_ms=quiet_ms, poll_ms=30,
                           max_wait_ms=2000, grace_ms=0, min_wait_ms=0,
                           blank_hash=7)
        assert ok is False, "declared a never-painted blank screen stable"
    body()


@SETTINGS
@given(quiet_ms=st.integers(min_value=10, max_value=200),
       nbytes=st.integers(min_value=1, max_value=8))
def prop_blank_gate_releases_after_output(quiet_ms, nbytes):
    """Once output HAS been seen, a screen equal to the blank baseline may settle.

    Otherwise a program that legitimately clears its screen could never be
    detected as ready — the gate must key on "never painted", not "looks blank".
    """
    @patched
    def body(clock):
        feed = Feed([(nbytes, 7)])  # output arrives, hash equals blank baseline
        ok, _ = run_stable(clock, feed, quiet_ms=quiet_ms, poll_ms=30,
                           max_wait_ms=4000, grace_ms=0, min_wait_ms=0,
                           blank_hash=7)
        assert ok is True, "blank gate kept blocking after real output arrived"
    body()


for fn, label in ((prop_min_wait_respected, "never settles before min_wait_ms"),
                  (prop_quiet_time_respected, "never settles before quiet_ms"),
                  (prop_always_terminates, "always terminates within its budget"),
                  (prop_blank_gate_never_settles, "blank screen never reads as stable"),
                  (prop_blank_gate_releases_after_output,
                   "blank gate releases once output is seen")):
    try:
        fn()
        report(label)
    except BaseException as exc:  # noqa: BLE001 — report, do not abort the file
        report(label, exc)


# --------------------------------------------------------------------------
print("\n--- wait_for_regex / wait_any invariants ---")


class TextFeed:
    """A screen whose text is revealed one scripted step at a time."""

    def __init__(self, steps: list[str]) -> None:
        self.steps = list(steps)
        self.index = 0
        self.text = ""

    def read(self) -> bytes:
        if self.index < len(self.steps):
            self.text = self.steps[self.index]
            self.index += 1
            return b"x"
        return b""

    def snapshot(self):
        return self.text


@SETTINGS
@given(steps=st.lists(st.sampled_from(["", "abc", "ready> ", "Error!", "Password:"]),
                      min_size=0, max_size=12),
       pattern=st.sampled_from(["ready> ", "Error", "Password:", "nomatch"]))
def prop_regex_only_true_when_present(steps, pattern):
    @patched
    def body(clock):
        feed = TextFeed(steps)
        # signature: (read_fn, get_text_fn, get_snapshot_fn, pattern, ...)
        matched, snap = readiness.wait_for_regex(
            feed.read, feed.snapshot, feed.snapshot, pattern,
            timeout_ms=2000, poll_ms=30)
        import re
        if matched:
            assert re.search(pattern, snap or ""), (
                f"reported a match for {pattern!r} against {snap!r}")
        else:
            # On timeout the caller must still receive the last screen.
            assert snap is not None or feed.text == ""
    body()


@SETTINGS
@given(steps=st.lists(st.sampled_from(["", "abc", "AB", "BA", "xyz"]),
                      min_size=0, max_size=12),
       patterns=st.lists(st.sampled_from(["A", "B", "zz"]), min_size=0, max_size=4))
def prop_wait_any_index_is_valid_and_earliest(steps, patterns):
    @patched
    def body(clock):
        feed = TextFeed(steps)
        index, snap = readiness.wait_any(
            feed.read, feed.snapshot, feed.snapshot, patterns,
            timeout_ms=2000, poll_ms=30)
        import re
        assert index == -1 or 0 <= index < len(patterns), f"index {index} out of range"
        if index >= 0:
            text = snap or ""
            assert re.search(patterns[index], text), (
                f"index {index} ({patterns[index]!r}) does not match {text!r}")
            # Earliest-in-list wins a same-poll tie.
            for earlier in range(index):
                assert not re.search(patterns[earlier], text), (
                    f"pattern {earlier} also matched {text!r}; should have won")
        else:
            assert not patterns or not any(
                re.search(p, feed.text) for p in patterns) or feed.index == 0, (
                "returned -1 while a pattern was on the final screen")
    body()


for fn, label in ((prop_regex_only_true_when_present,
                   "wait_for_regex reports True only on a real match"),
                  (prop_wait_any_index_is_valid_and_earliest,
                   "wait_any returns a valid, earliest-matching index")):
    try:
        fn()
        report(label)
    except BaseException as exc:  # noqa: BLE001
        report(label, exc)


if FAILURES:
    print(f"\ntest_readiness_properties FAIL -- {len(FAILURES)} propert(ies):")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("\nPASS: the wait primitives hold their invariants across "
      "Hypothesis-generated schedules.")
sys.exit(0)
