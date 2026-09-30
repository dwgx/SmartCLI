#!/usr/bin/env python3
"""test_revision_baseline.py — a wait baseline that is a STATE, not a duration.

Every other readiness knob is a guess about time: `min_wait_ms=50` to dodge the
stale screen, `quiet_ms=200` to call it settled. A guess cannot separate two
situations that look identical from inside the loop:

  * the program is still working, or
  * the program finished BEFORE the wait began and the answer is already
    painted on the screen.

Both satisfy "nothing changed recently", and the second is reported as success.
`agent-tty` (coder) answers this with `--after-seq`: a wait BASELINE — "wait
until the screen has changed since sequence S" — rather than a wait DURATION.
This gate locks that ours can too.

Covered here:
  * `PtySession.screen_revision()` is MONOTONIC and counts CHANGES, not
    observations: an identical repaint (the same bytes drawn again, a cursor
    move, a re-read) must not advance it, and a real text change must,
  * the anchor suppresses a wait's success while closed — a marker already on
    the pre-anchor screen is not a match, and pre-anchor stillness is not
    stability — across all four readiness primitives plus both hash-change waits,
  * an anchored wait RETURNS as soon as the screen moves (measured in virtual
    time, so "as soon as" is a number), and FALLS BACK TO THE DEADLINE when the
    screen never moves, instead of hanging or reporting the stale screen,
  * the FOUR-WAY composition: anchor x content x child-death x deadline, with
    the two orderings that matter stated as decisions — a child that dies while
    the anchor is still closed is EXITED (a dead child is a fact about the world,
    not a screen that failed to change), and a child that dies on the same poll
    the anchor opens is still reported through the CONTENT branch,
  * the anchor gates SUCCESS ONLY: an anchored wait that never sees a change
    still returns at its `max_wait_ms` ceiling, on every one of the four
    primitives — the anchored twin of `test_readiness.py`'s "respected max_wait
    ceiling", which cannot see a ceiling wrongly gated behind the anchor
    because it supplies none,
  * the default path is untouched: with no `after_revision` every primitive
    behaves exactly as before, including the pre-existing outcomes.

Pure/in-memory: scripted callables, a fake backend, and a real pyte screen
model. No PTY, no child process, and a virtual clock for every readiness-level
case — nothing here sleeps for real.
"""
from __future__ import annotations

import os
import sys
import threading
import time as _real_time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core import PtySession, readiness  # noqa: E402
from smartcli_core.pty_backend import PtyBackend  # noqa: E402

_fails: list[str] = []


# Whole-file wall-clock budget. The file really costs about 1.1 s, so this is
# ~50x headroom: it exists to catch a wait that is not going to finish, not to
# police a slow machine. It is the only bound that reaches the session-level
# tests, which measure real time on purpose.
SUITE_BUDGET_S = 60.0


def check(cond, name, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {name}  {detail}")
    if not cond:
        _fails.append(name)


class VirtualRunaway(Exception):
    """A wait drove virtual time past the clock's horizon without returning.

    The only way out of a readiness loop is a `return`, so a broken ceiling has
    to be escaped from the outside — by making the clock itself refuse to keep
    lending time. Without this the file HANGS on a regression that removes the
    deadline, which is worse than failing: a timeout is reported as an
    infrastructure problem, not as the assertion it is.
    """


# -- virtual clock --------------------------------------------------------
# Same trick as test_readiness.py / test_child_death_wait.py: readiness calls
# `time.monotonic()`/`sleep()`, so replacing them on the `time` module it
# imported makes every loop advance virtual time instead of really waiting.
# Installed only around the readiness-level tests so the session-level
# wall-clock measurements below are real.
# `VirtualRunaway` is the escape hatch: a wait that ignores its ceiling never
# RETURNS, so nothing downstream can assert on it — the loop has to be broken
# from the outside. The clock refusing to lend time past a horizon is what turns
# "the deadline is gone" into a reported FAIL rather than a file that hangs.

class VirtualClock:
    # Generous: the longest legitimate wait in this file is a 30 s ceiling at a
    # 30 ms poll (1000 sleeps). The horizon only has to be well clear of that,
    # and low enough that a runaway is caught in well under a second of real
    # time — time.sleep is free here, so the horizon costs iterations, not
    # seconds.
    HORIZON_S = 120.0

    def __init__(self, horizon_s: float | None = None) -> None:
        self.t = 0.0
        self.last_sleep = None
        self.horizon_s = self.HORIZON_S if horizon_s is None else horizon_s

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.last_sleep = seconds
        self.t += seconds if seconds > 0 else 0.001
        if self.t > self.horizon_s:
            raise VirtualRunaway(
                f"virtual time passed {self.horizon_s:g}s with the wait still polling: "
                "its max_wait ceiling was never reached")


class clock_installed:
    """Context manager: virtual time inside, real time restored outside.

    ``horizon_s`` bounds how much virtual time the clock will lend; pass it
    only to assert a specific ceiling. The default keeps a runaway wait from
    hanging the whole file, which is what turns "the deadline is gone" into a
    reported failure instead of a CI timeout.
    """

    def __init__(self, horizon_s: float | None = None) -> None:
        self._horizon_s = horizon_s

    def __enter__(self) -> VirtualClock:
        self.clk = VirtualClock(self._horizon_s)
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


def changes_after(n):
    """changed_since: closed for the first ``n`` polls, open from poll n+1 on."""
    state = {"calls": 0}

    def _changed():
        state["calls"] += 1
        return state["calls"] > n

    _changed.calls = state          # type: ignore[attr-defined]
    return _changed


def never_changes():
    """changed_since: an anchor that never opens (nothing ever moves)."""
    return lambda: False


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


def seq_reader(batches):
    """read_fn feeding ``batches`` in order, then b'' forever."""
    it = iter(batches)

    def _read():
        return next(it, b"")

    return _read


def feeding_reader(screen, batches):
    """read_fn feeding ``batches`` into ``screen`` in order, then b'' forever."""
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
# readiness.wait_until_stable — the anchor vs pre-anchor stillness
# =========================================================================

def test_stable_anchor_blocks_pre_anchor_stillness():
    """A permanently still screen is STABLE unanchored and NOT stable anchored."""
    with clock_installed() as clk:
        unanchored = readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=0,
        )
        t_unanchored = clk.t
        clk.t = 0.0
        anchored = readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=0,
            changed_since=never_changes(),
        )
        t_anchored = clk.t
    check(unanchored is True,
          "wait_until_stable: a still screen settles when unanchored",
          f"virt_t={t_unanchored:.2f}s")
    check(anchored is False,
          "wait_until_stable: an anchor that never opens cannot settle",
          f"res={anchored!r}")
    check(t_anchored >= 30.0,
          "wait_until_stable: a closed anchor falls back to the DEADLINE, not a hang",
          f"virt_t={t_anchored:.2f}s")


def test_stable_returns_as_soon_as_the_anchor_opens_and_the_screen_settles():
    """Anchored: opens on poll 4, then needs a full quiet window served AFTER it.

    The claim under test is that the anchor RESETS the quiet timer rather than
    merely delaying it: an unanchored wait on this screen settles at 210ms (the
    quiet window starts on poll 1), and the anchored one must not settle before
    the change it is anchored to plus a fresh 200ms.
    """
    with clock_installed() as clk:
        readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=0,
        )
        t_unanchored = clk.t
    with clock_installed() as clk:
        res = readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=0,
            changed_since=changes_after(3),
        )
        t = clk.t
    check(res is True, "wait_until_stable: anchored wait succeeds once the screen moves",
          f"res={res!r}")
    # The anchor opens on poll 4, at t=90ms. The quiet window can only be served
    # from there, so the earliest honest return is 90+200=290ms -- later than the
    # unanchored 210ms, which is the whole point: the pre-anchor stillness does
    # not count toward settling.
    check(t >= 0.09 + 0.2,
          "wait_until_stable: quiet is served AFTER the change, not before it",
          f"anchored={t * 1000:.0f}ms unanchored={t_unanchored * 1000:.0f}ms")
    check(t > t_unanchored,
          "wait_until_stable: anchoring strictly delays the settle past the unanchored one",
          f"anchored={t * 1000:.0f}ms unanchored={t_unanchored * 1000:.0f}ms")


def test_stable_anchor_open_at_once_still_needs_quiet():
    """Anchor open from poll 1: no change happened, so the change must land.

    ``changes_after(0)`` models "the screen moved before I anchored" — that is
    NOT the same as "the screen is quiet now", and the wait must still serve a
    quiet window off a real observation rather than returning instantly off the
    pre-anchor stillness.
    """
    with clock_installed() as clk:
        res = readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=0,
            changed_since=changes_after(0),
        )
        t = clk.t
    check(res is True and t >= 0.2,
          "wait_until_stable: an already-open anchor still waits out its quiet window",
          f"res={res!r} virt_t={t:.2f}s")


# =========================================================================
# readiness.wait_for_regex / wait_any — a marker already on screen
# =========================================================================

def test_regex_ignores_a_match_that_was_already_on_the_pre_anchor_screen():
    with clock_installed() as clk:
        matched, _ = readiness.wait_for_regex(
            read_fn=noop_reader(), get_text_fn=lambda: ">>> ",
            get_snapshot_fn=lambda: "SNAP", pattern=r">>> ",
            timeout_ms=30000, poll_ms=30, changed_since=never_changes(),
        )
        t = clk.t
    check(matched is False,
          "wait_for_regex: a marker already showing is not reported through a closed anchor",
          f"matched={matched!r}")
    check(t >= 30.0,
          "wait_for_regex: closed anchor → deadline, not a hang", f"virt_t={t:.2f}s")


def test_regex_reports_the_match_once_the_anchor_opens():
    with clock_installed() as clk:
        matched, _ = readiness.wait_for_regex(
            read_fn=noop_reader(), get_text_fn=lambda: ">>> ",
            get_snapshot_fn=lambda: "SNAP", pattern=r">>> ",
            timeout_ms=30000, poll_ms=30, changed_since=changes_after(2),
        )
        t = clk.t
    check(matched is True, "wait_for_regex: the same match IS reported once the anchor opens",
          f"matched={matched!r}")
    # changes_after(2) opens on poll 3, i.e. after two 30ms sleeps.
    check(0.06 <= t < 0.5,
          "wait_for_regex: returns on the first open poll, not at the ceiling",
          f"virt_t={t:.3f}s")


def test_any_ignores_a_pattern_that_was_already_matching():
    with clock_installed() as clk:
        idx, _ = readiness.wait_any(
            read_fn=noop_reader(), get_text_fn=lambda: "Traceback (most recent call last)",
            get_snapshot_fn=lambda: "SNAP", patterns=[r">>> ", r"Traceback"],
            timeout_ms=30000, poll_ms=30, changed_since=never_changes(),
        )
        t = clk.t
    check(idx == -1,
          "wait_any: an already-matching pattern is not reported through a closed anchor",
          f"idx={idx!r}")
    check(t >= 30.0, "wait_any: closed anchor → deadline", f"virt_t={t:.2f}s")

    with clock_installed() as clk:
        idx2, _ = readiness.wait_any(
            read_fn=noop_reader(), get_text_fn=lambda: "Traceback (most recent call last)",
            get_snapshot_fn=lambda: "SNAP", patterns=[r">>> ", r"Traceback"],
            timeout_ms=30000, poll_ms=30, changed_since=changes_after(1),
        )
        t2 = clk.t
    check(idx2 == 1,
          "wait_any: the same match IS reported once the anchor opens (earliest-index rule kept)",
          f"idx={idx2!r}")
    # changes_after(1) opens on poll 2, i.e. after one 30ms sleep.
    check(0.03 <= t2 < 0.5, "wait_any: returns on the first open poll", f"virt_t={t2:.3f}s")


# =========================================================================
# readiness.wait_ready — both branches, and the marker/death race
# =========================================================================

def test_ready_marker_is_withheld_while_the_anchor_is_closed():
    with clock_installed() as clk:
        reason, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            get_text_fn=lambda: ">>> ready", get_snapshot_fn=lambda: "SNAP",
            marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=30000, min_wait_ms=0,
            grace_ms=0, changed_since=never_changes(),
        )
        t = clk.t
    check(reason == "TIMEOUT",
          "wait_ready: a marker already on screen is not MARKER through a closed anchor",
          f"reason={reason}")
    check(t >= 30.0, "wait_ready: closed anchor → TIMEOUT at the deadline", f"virt_t={t:.2f}s")


def test_ready_marker_wins_on_the_poll_the_anchor_opens():
    """The change and the marker are visible on the SAME poll: MARKER, not TIMEOUT."""
    with clock_installed():
        reason, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            get_text_fn=lambda: ">>> ready", get_snapshot_fn=lambda: "SNAP",
            marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=30000, min_wait_ms=0,
            grace_ms=0, changed_since=changes_after(1),
        )
    check(reason == "MARKER",
          "wait_ready: the anchor opens on the poll the marker is visible → MARKER",
          f"reason={reason}")


def test_ready_stable_also_withheld_by_the_anchor():
    """STABLE is gated too: pre-anchor stillness must not be called readiness."""
    with clock_installed() as clk:
        reason, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            get_text_fn=lambda: "idle", get_snapshot_fn=lambda: "SNAP",
            marker=None, quiet_ms=200, poll_ms=30, max_wait_ms=30000, min_wait_ms=0,
            grace_ms=0, changed_since=never_changes(),
        )
        t = clk.t
    check(reason == "TIMEOUT",
          "wait_ready: STABLE is gated by the anchor just as MARKER is",
          f"reason={reason}")
    check(t >= 30.0, "wait_ready: closed anchor → TIMEOUT, not STABLE", f"virt_t={t:.2f}s")


# =========================================================================
# The four-way composition: anchor x content x death x deadline
# =========================================================================

def test_anchor_plus_death_is_exited_while_the_anchor_is_still_closed():
    """A child that dies before the screen moves: EXITED, promptly.

    The asymmetry is the point. A dead child is a fact about the WORLD, not a
    screen that failed to change; gating the death outcome behind the anchor
    would make a crash cost the entire ceiling again, which is the bug
    ``alive_fn`` was added to fix. So the death branch is reachable while the
    anchor is closed.
    """
    with clock_installed() as clk:
        res = readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=0,
            changed_since=never_changes(), alive_fn=dies_after(2),
        )
        t = clk.t
    check(res is readiness.EXITED,
          "wait_until_stable: dead child under a closed anchor → EXITED, not the ceiling",
          f"res={res!r}")
    check(t < 1.0, "wait_until_stable: EXITED arrives in one poll cycle, not 30s",
          f"virt_t={t:.3f}s")


def test_anchor_plus_death_plus_never_changes_never_hangs():
    """Both axes engaged, nothing on screen ever moves: still exits promptly."""
    shared = dict(read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
                  get_text_fn=lambda: "", get_snapshot_fn=lambda: "SNAP",
                  poll_ms=30, max_wait_ms=30000, grace_ms=0, min_wait_ms=0,
                  quiet_ms=200, changed_since=never_changes(),
                  alive_fn=dies_after(2))
    with clock_installed() as clk:
        res_stable = readiness.wait_until_stable(
            **{k: v for k, v in shared.items()
               if k not in ("get_text_fn", "get_snapshot_fn", "min_wait_ms")})
        t_stable = clk.t
    check(t_stable < 1.0,
          "wait_until_stable: anchor closed AND child dead → exits promptly, never hangs",
          f"res={res_stable!r} virt_t={t_stable:.3f}s")

    with clock_installed() as clk:
        res_ready, _ = readiness.wait_ready(**shared)
        t_ready = clk.t
    check(t_ready < 1.0 and res_ready == readiness.EXITED_REASON,
          "wait_ready: anchor closed AND child dead → EXITED promptly, never hangs",
          f"reason={res_ready!r} virt_t={t_ready:.3f}s")


def test_anchor_opening_on_the_poll_the_child_dies_is_reported_as_content():
    """The anchor and the marker both open on the death poll: content wins.

    Same rule ``alive_fn`` established for the MARKER/death race — the content
    condition is evaluated first, so information the agent sent the wait for is
    not thrown away — extended to the anchor, which is just one more content
    condition on the same poll.
    """
    # A GENUINE same-poll race, built by shifting ONE input at a time:
    #   screen — the traceback is fed on poll 1, so it is visible from poll 2 on
    #   anchor — closed on poll 1, opens on poll 2
    #   death  — alive on poll 1, dead from poll 2
    # So on poll 2 the anchor opens, the marker is visible AND the child is gone.
    def run(changed_since, alive_fn):
        screen = FakeScreen()
        with clock_installed():
            reason, _ = readiness.wait_ready(
                read_fn=feeding_reader(screen, [b"Traceback (most recent call last)"]),
                get_screen_hash_fn=screen.hash,
                get_text_fn=screen.text, get_snapshot_fn=screen.snapshot,
                marker=r"Traceback", quiet_ms=200, poll_ms=30, max_wait_ms=30000,
                min_wait_ms=0, grace_ms=0,
                changed_since=changed_since, alive_fn=alive_fn,
            )
        return reason

    won = run(changes_after(1), dies_after(1))
    # Same inputs, death one poll earlier: the child is gone while the anchor is
    # still closed, so there is no marker to report and EXITED is the answer.
    lost = run(changes_after(1), dies_after(0))

    check(won == "MARKER",
          "wait_ready: anchor opens + marker visible + child dies on the SAME poll "
          "→ MARKER (content wins the race, as with alive_fn alone)",
          f"reason={won}")
    check(lost == readiness.EXITED_REASON,
          "wait_ready: same inputs, child died one poll earlier → EXITED; the anchor "
          "suppresses success, never the death outcome",
          f"reason={lost}")


def test_anchor_plus_alive_plus_never_changes_times_out_not_stable():
    """Child alive, anchor never opens: the ordinary timeout, at the ceiling."""
    with clock_installed() as clk:
        reason, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            get_text_fn=lambda: "idle", get_snapshot_fn=lambda: "SNAP",
            marker=None, quiet_ms=200, poll_ms=30, max_wait_ms=30000, min_wait_ms=0,
            grace_ms=0, changed_since=never_changes(), alive_fn=always_alive(),
        )
        t = clk.t
    check(reason == "TIMEOUT",
          "wait_ready: alive child + closed anchor → TIMEOUT (STABLE withheld)", f"reason={reason}")
    check(t >= 30.0, "wait_ready: …and it runs to the ceiling", f"virt_t={t:.2f}s")


def test_a_closed_anchor_never_gates_the_ceiling_on_any_primitive():
    """The anchored twin of test_readiness.py's "respected max_wait ceiling".

    ``readiness.py`` claims in three places that the revision anchor "suppresses
    success only -- never the max_wait ceiling" (module docstring:23-24, the
    ``changed_since`` docstring:253-255, and ``_anchor_open``:204-213). Every
    anchored check above asserts the SUCCESS half of that claim, so none of them
    can tell "gates success" from "gates everything".

    The check that could is the unanchored one at ``test_readiness.py:138``,
    titled "respected max_wait ceiling" -- and it is blind, because it supplies
    no ``changed_since``, so ``_anchor_open(None)`` is True and a ceiling that
    were wrongly gated behind the anchor would be behaviourally identical. The
    anchored twin has to be stated here, explicitly, for all four primitives:
    a screen that never changes, an anchor that never opens, and a wait that
    must still come back at ``max_wait_ms``.

    Each call runs under a clock horizon five times its own ceiling, so a wait
    that outlives its ceiling raises :class:`VirtualRunaway` and is reported as
    a FAILED check instead of spinning until the suite is killed. A green run
    here means the ceiling was reached; the horizon is what makes the check able
    to say so about a red one too.
    """
    CEILING_MS = 1000
    CEILING_S = CEILING_MS / 1000
    HORIZON_S = 5.0  # 5x the ceiling: roomy for correct code, finite for broken

    def at_ceiling(label, expected, call):
        """One anchored wait; assert it came back AT its ceiling, not sooner/later.

        ``expected`` is what the primitive returns when its ceiling is what ended
        the wait — False for the two boolean waits, the TIMEOUT reason for
        ``wait_ready``, -1 for ``wait_any``. A wait that ignored its ceiling
        raises :class:`VirtualRunaway` at the horizon and is reported here as a
        FAILED check, which is the whole reason the horizon exists: the failure
        mode of a missing deadline is a hang, and a hang cannot fail a gate.
        """
        with clock_installed(horizon_s=HORIZON_S) as clk:
            try:
                result = call()
            except VirtualRunaway as exc:
                check(False, f"{label}: a closed anchor does not gate the max_wait ceiling",
                      f"RUNAWAY — {exc}")
                return
            t = clk.t
        check(result == expected and CEILING_S <= t < HORIZON_S,
              f"{label}: a closed anchor does not gate the max_wait ceiling",
              f"res={result!r} virt_t={t:.2f}s (ceiling={CEILING_S}s, horizon={HORIZON_S}s)")

    # 1) wait_until_stable — the primitive mutation M15 was applied to.
    at_ceiling("wait_until_stable", False, lambda: readiness.wait_until_stable(
        read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
        quiet_ms=200, poll_ms=30, max_wait_ms=CEILING_MS, grace_ms=0,
        changed_since=never_changes()))

    # 2) wait_ready — the reason string a caller actually branches on. No
    #    marker and a still screen, so STABLE is withheld too: the ceiling is
    #    the only thing left that can end this wait, and it must.
    at_ceiling("wait_ready", "TIMEOUT", lambda: readiness.wait_ready(
        read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
        get_text_fn=lambda: "idle", get_snapshot_fn=lambda: "SNAP",
        marker=None, quiet_ms=200, poll_ms=30, max_wait_ms=CEILING_MS,
        min_wait_ms=0, grace_ms=0, changed_since=never_changes())[0])

    # 3) wait_for_regex — a marker already on the pre-anchor screen: withheld as
    #    a MATCH, but the timeout is not withheld with it.
    at_ceiling("wait_for_regex", False, lambda: readiness.wait_for_regex(
        read_fn=noop_reader(), get_text_fn=lambda: ">>> ",
        get_snapshot_fn=lambda: "SNAP", pattern=r">>> ",
        timeout_ms=CEILING_MS, poll_ms=30, changed_since=never_changes())[0])

    # 4) wait_any — the same shape, the index-returning primitive.
    at_ceiling("wait_any", -1, lambda: readiness.wait_any(
        read_fn=noop_reader(), get_text_fn=lambda: ">>> ",
        get_snapshot_fn=lambda: "SNAP", patterns=[r">>> "],
        timeout_ms=CEILING_MS, poll_ms=30, changed_since=never_changes())[0])


# =========================================================================
# The default path is untouched
# =========================================================================

def test_default_path_has_no_anchor_object_at_all():
    """``changed_since=None`` must mean "no predicate", not "a lambda returning True".

    A wrapper would work but would pay a call per poll forever and would make
    the untouched default indistinguishable from the anchored one by
    construction. This is the same bargain ``alive_fn`` makes, asserted.
    """
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend())
    check(sess._changed_since(None) is None,
          "PtySession: no after_revision → no anchor predicate at all")
    check(sess._changed_since(0) is not None,
          "PtySession: an explicit after_revision → a predicate")


def test_default_path_results_are_unchanged():
    """Every primitive, unanchored, returns exactly its pre-existing outcome."""
    with clock_installed() as clk:
        stable = readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=1000, grace_ms=0)
    check(stable is True, "wait_until_stable unanchored: still settles", f"res={stable!r}")

    with clock_installed():
        matched, _ = readiness.wait_for_regex(
            read_fn=noop_reader(), get_text_fn=lambda: ">>> now",
            get_snapshot_fn=lambda: "S", pattern=r">>> ", timeout_ms=1000, poll_ms=30)
    check(matched is True, "wait_for_regex unanchored: still matches immediately",
          f"matched={matched!r}")

    with clock_installed():
        idx, _ = readiness.wait_any(
            read_fn=noop_reader(), get_text_fn=lambda: ">>> now",
            get_snapshot_fn=lambda: "S", patterns=[r">>> "], timeout_ms=1000, poll_ms=30)
    check(idx == 0, "wait_any unanchored: still reports index 0", f"idx={idx!r}")

    with clock_installed():
        reason, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            get_text_fn=lambda: "idle", get_snapshot_fn=lambda: "S",
            marker=None, quiet_ms=100, poll_ms=30, max_wait_ms=1000, min_wait_ms=0,
            grace_ms=0)
    check(reason == "STABLE", "wait_ready unanchored: still settles", f"reason={reason}")

    with clock_installed() as clk:
        timed_out, _ = readiness.wait_ready(
            read_fn=noop_reader(), get_screen_hash_fn=churning_hash(),
            get_text_fn=lambda: "busy", get_snapshot_fn=lambda: "S",
            marker=r">>> ", quiet_ms=200, poll_ms=30, max_wait_ms=30000, min_wait_ms=0)
        t = clk.t
    check(timed_out == "TIMEOUT" and t >= 30.0,
          "wait_ready unanchored: a churning screen still sits out the ceiling",
          f"reason={timed_out} virt_t={t:.2f}s")


def test_a_supplied_anchor_is_actually_consulted_every_poll():
    """The gate is live, not decorative: a supplied predicate is called per poll.

    The companion to ``_changed_since(None) is None``: that one proves an
    UNanchored wait carries no predicate, and this one proves an anchored wait
    really evaluates the predicate on each poll rather than quietly ignoring it.
    A dead gate would make every anchored assertion above pass for the wrong
    reason (they would be testing the ordinary timeout path).
    """
    counted = changes_after(2)
    with clock_installed():
        res = readiness.wait_until_stable(
            read_fn=noop_reader(), get_screen_hash_fn=constant_hash(),
            quiet_ms=200, poll_ms=30, max_wait_ms=30000, grace_ms=0,
            changed_since=counted)
    polls = counted.calls["calls"]
    check(polls >= 3,
          "a supplied anchor is consulted on every poll until it opens",
          f"calls={polls} res={res!r}")


# =========================================================================
# PtySession.screen_revision — monotonic, and change-counting not poll-counting
# =========================================================================

class ScriptBackend(PtyBackend):
    """Fake backend whose read queue is drained one chunk per read."""

    def __init__(self, chunks=(), die_after=None):
        self._q = list(chunks)
        self._alive = True
        self._reads = 0
        self._die_after = die_after

    def queue(self, data):
        self._q.append(data)

    def spawn(self, cmd, cols, rows):
        pass

    def read_nonblocking(self, timeout=0.0):
        self._reads += 1
        if self._die_after is not None and self._reads >= self._die_after:
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


def test_revision_counts_changes_not_observations():
    """The first observation is the baseline; an identical repaint is not a change."""
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend())
    check(sess.screen_revision() == 0,
          "the first observation establishes the baseline, it is not a change",
          f"rev={sess.screen_revision()}")
    for _ in range(5):
        sess.screen_revision()
    check(sess.screen_revision() == 0,
          "re-reading an unchanging screen never advances the revision",
          f"rev={sess.screen_revision()}")

    be = sess.backend
    # Home + write, so the SAME bytes redraw the SAME cells: an identical
    # repaint, which is what a shell echoing its prompt in a loop looks like.
    be.queue(b"\x1b[Hhello")
    sess.pump()
    check(sess.screen_revision() == 1,
          "real output advances the revision exactly once", f"rev={sess.screen_revision()}")
    check(sess.screen_revision() == 1,
          "and it stays there while the screen holds still", f"rev={sess.screen_revision()}")

    be.queue(b"\x1b[Hhello")
    sess.pump()
    check(sess.screen_revision() == 1,
          "an identical repaint is not a change (revision tracks the SCREEN, not the bytes)",
          f"rev={sess.screen_revision()}")

    be.queue(b"\x1b[Hworld")
    sess.pump()
    check(sess.screen_revision() == 2,
          "different visible text advances it again", f"rev={sess.screen_revision()}")


def test_revision_is_monotonic_across_polls():
    """Backwards text (a TUI rewriting earlier cells) still moves it forward."""
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend())
    seen = [sess.screen_revision()]
    for chunk in (b"aaa", b"bbb", b"aaa", b"ccc"):
        sess.backend.queue(chunk)
        sess.pump()
        seen.append(sess.screen_revision())
    check(seen == sorted(seen) and seen == [0, 1, 2, 3, 4],
          "every real change advances by one and never goes backwards", f"revisions={seen}")


def test_revision_is_not_reset_by_start():
    """A pending anchor must never be satisfied by a counter that went backwards."""
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend())
    sess.backend.queue(b"first")
    sess.pump()
    before = sess.screen_revision()
    sess.backend.queue(b"second")
    sess.pump()
    sess.start("does-not-run")
    after = sess.screen_revision()
    check(after >= before,
          "start() does not rewind the revision", f"before={before} after={after}")


# =========================================================================
# PtySession threading — the public affordance end to end
# =========================================================================

def test_session_anchored_stable_waits_for_the_change_then_settles():
    """The real affordance: read the screen, send input, wait for a response."""
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend([b"old prompt> "]))
    sess.pump()
    anchor = sess.screen_revision()
    sess.backend.queue(b"new prompt> ")
    settled = sess.wait_stable(quiet_ms=100, max_wait_ms=3000, grace_ms=0,
                              after_revision=anchor)
    check(settled is True,
          "PtySession.wait_stable(after_revision=…): a real response settles the wait",
          f"res={settled!r}")
    check(sess.screen_revision() > anchor,
          "…and the revision advanced past the anchor", f"anchor={anchor}")


def test_session_anchored_stable_with_no_response_times_out():
    """No output at all: the anchor holds and the wait falls back to its ceiling."""
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend([b"old prompt> "]))
    sess.pump()
    anchor = sess.screen_revision()
    settled = sess.wait_stable(quiet_ms=100, max_wait_ms=250, grace_ms=0,
                              after_revision=anchor)
    check(settled is False,
          "PtySession.wait_stable(after_revision=…): silence is a TIMEOUT, not 'settled'",
          f"res={settled!r}")


def test_session_anchored_marker_ignores_a_prompt_that_was_already_there():
    """The motivating case: the prompt is on screen BEFORE the anchor."""
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend([b">>> "]))
    sess.pump()
    anchor = sess.screen_revision()

    # Unanchored: matches instantly on the screen that was already there.
    sess2 = PtySession(cols=40, rows=10, backend=ScriptBackend([b">>> "]))
    sess2.pump()
    unanchored, _ = sess2.wait_for(r">>> ", timeout_ms=300, poll_ms=20)
    check(unanchored is True,
          "unanchored wait_for: the already-there prompt matches (pre-existing behaviour)",
          f"matched={unanchored!r}")

    # Anchored at that same screen: it is not news, so the wait must run out.
    anchored, _ = sess.wait_for(r">>> ", timeout_ms=300, poll_ms=20,
                                after_revision=anchor)
    check(anchored is False,
          "anchored wait_for: the same prompt is NOT reported — nothing changed since I looked",
          f"matched={anchored!r}")

    # …and once the program really prints a new one, the anchored wait fires.
    sess.backend.queue(b"new >>> ")
    sess.pump()
    fired, _ = sess.wait_for(r">>> ", timeout_ms=500, poll_ms=20, after_revision=anchor)
    check(fired is True,
          "anchored wait_for: a genuinely new prompt is reported once the screen moves",
          f"matched={fired!r}")


def test_session_anchored_change_requires_both_axes():
    """wait_change: the baseline says different, the anchor says moved — both needed.

    Neither axis subsumes the other. The baseline hash answers "is the screen
    different from what I sampled"; the revision answers "has anything happened
    at all since I looked". With the baseline default (sampled at call time) a
    change that already landed is folded in and the wait correctly times out —
    which is exactly the case the anchor exists to make the caller state
    explicitly rather than infer from a duration.
    """
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend([b"\x1b[Hbefore"]))
    sess.pump()
    anchor = sess.screen_revision()
    baseline = sess.model.content_hash()

    # Baseline says "different" but the anchor is unreachable (a revision from
    # the future): the AND must still withhold success.
    changed, _ = sess.wait_change(baseline_hash=baseline, timeout_ms=200,
                                  poll_ms=20, after_revision=anchor + 1000)
    check(changed is False,
          "wait_change: baseline satisfied but anchor not → still no success",
          f"changed={changed!r}")

    # Both satisfied: the screen really moved past the anchor.
    sess.backend.queue(b"\x1b[Hafter")
    changed2, _ = sess.wait_change(baseline_hash=baseline, timeout_ms=500,
                                   poll_ms=20, after_revision=anchor)
    check(changed2 is True,
          "wait_change: baseline AND anchor both satisfied → success",
          f"changed={changed2!r}")


def test_session_anchor_plus_death_is_exited_promptly():
    """End to end: anchored AND a crashing child → EXITED in one poll cycle."""
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend(die_after=3))
    sess.pump()
    anchor = sess.screen_revision()
    sess.detect_child_exit = True
    t0 = _real_time.monotonic()
    settled = sess.wait_stable(quiet_ms=100, max_wait_ms=5000, grace_ms=0,
                              after_revision=anchor)
    elapsed_ms = (_real_time.monotonic() - t0) * 1000
    check(settled is readiness.EXITED,
          "PtySession: anchor + dead child → EXITED, not the 5s ceiling", f"res={settled!r}")
    check(elapsed_ms < 1000,
          "PtySession: …and it comes back in a poll cycle", f"elapsed={elapsed_ms:.0f}ms")


def test_session_default_path_is_unchanged():
    """No after_revision anywhere → the pre-existing results, unchanged."""
    sess = PtySession(cols=40, rows=10, backend=ScriptBackend([b"idle"]))
    sess.pump()
    settled = sess.wait_stable(quiet_ms=50, max_wait_ms=500, grace_ms=0)
    check(settled is True,
          "PtySession.wait_stable with no anchor: stillness is still stability",
          f"res={settled!r}")

    sess2 = PtySession(cols=40, rows=10, backend=ScriptBackend([b">>> "]))
    sess2.pump()
    reason, _ = sess2.wait_ready(marker=r">>> ", max_wait_ms=500, min_wait_ms=0)
    check(reason == "MARKER",
          "PtySession.wait_ready with no anchor: MARKER as before", f"reason={reason}")


def _run(functions) -> None:
    for fn in functions:
        # The clock's horizon turns a runaway readiness loop into an ordinary
        # reported FAIL and lets the tests after it still run, so one runaway
        # cannot hide the state of everything else.
        try:
            fn()
        except VirtualRunaway as exc:
            check(False, f"{fn.__name__}: a wait outlived its max_wait ceiling", str(exc))


def main() -> int:
    t0 = _real_time.perf_counter()
    print("=" * 68)
    print("revision baselines: a wait anchored to a STATE, not a duration")
    print("=" * 68)
    functions = (
        test_stable_anchor_blocks_pre_anchor_stillness,
        test_stable_returns_as_soon_as_the_anchor_opens_and_the_screen_settles,
        test_stable_anchor_open_at_once_still_needs_quiet,
        test_regex_ignores_a_match_that_was_already_on_the_pre_anchor_screen,
        test_regex_reports_the_match_once_the_anchor_opens,
        test_any_ignores_a_pattern_that_was_already_matching,
        test_ready_marker_is_withheld_while_the_anchor_is_closed,
        test_ready_marker_wins_on_the_poll_the_anchor_opens,
        test_ready_stable_also_withheld_by_the_anchor,
        test_anchor_plus_death_is_exited_while_the_anchor_is_still_closed,
        test_anchor_plus_death_plus_never_changes_never_hangs,
        test_anchor_opening_on_the_poll_the_child_dies_is_reported_as_content,
        test_anchor_plus_alive_plus_never_changes_times_out_not_stable,
        test_a_closed_anchor_never_gates_the_ceiling_on_any_primitive,
        test_default_path_has_no_anchor_object_at_all,
        test_default_path_results_are_unchanged,
        test_a_supplied_anchor_is_actually_consulted_every_poll,
        test_revision_counts_changes_not_observations,
        test_revision_is_monotonic_across_polls,
        test_revision_is_not_reset_by_start,
        test_session_anchored_stable_waits_for_the_change_then_settles,
        test_session_anchored_stable_with_no_response_times_out,
        test_session_anchored_marker_ignores_a_prompt_that_was_already_there,
        test_session_anchored_change_requires_both_axes,
        test_session_anchor_plus_death_is_exited_promptly,
        test_session_default_path_is_unchanged,
    )
    # The session-level tests measure REAL wall-clock time, so no virtual
    # horizon can reach them: an anchored session wait whose deadline was
    # removed spins there forever. The suite therefore also runs on a worker
    # under a wall-clock budget, so a missing ceiling ANYWHERE in this file ends
    # as a reported FAIL with a verdict rather than a CI job killed at its
    # timeout with no output. The budget is ~50x what the file really costs
    # (~1.1 s), so it can only fire on a wait that is not going to finish.
    worker = threading.Thread(target=_run, args=(functions,), daemon=True)
    worker.start()
    worker.join(SUITE_BUDGET_S)
    if worker.is_alive():
        check(False, f"the suite exceeded its {SUITE_BUDGET_S:g}s wall budget",
              "a wait is still polling: some ceiling is not being enforced")
        print("-" * 68)
        print(f"FAIL: {len(_fails)} check(s) failed: {_fails}")
        sys.stdout.flush()
        # os._exit, not sys.exit: the worker is still inside a readiness loop
        # and would keep the interpreter alive through a normal shutdown.
        os._exit(1)
    wall = _real_time.perf_counter() - t0
    print("-" * 68)
    if _fails:
        print(f"FAIL: {len(_fails)} check(s) failed: {_fails}")
        return 1
    print(f"PASS: waits can be anchored to a revision, in {wall*1000:.0f} ms wall")
    return 0


if __name__ == "__main__":
    sys.exit(main())