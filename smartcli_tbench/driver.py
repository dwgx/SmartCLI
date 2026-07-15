"""driver.py — SmartCLI's wait primitives over a Terminal-Bench TmuxSession.

TB's ``TmuxSession`` exposes ``send_keys(keys, block=…)``, ``capture_pane()`` (the
rendered pane text) and ``get_incremental_output()``. It already returns
terminal-processed text, so — unlike ``smartcli_core`` — there's no pyte model to
run; perception IS ``capture_pane()``. What the stock naive agent lacks, and what
makes driving interactive TUIs reliable, is the *synchronisation*: after acting,
wait until the screen actually settles / shows a marker / changes. This module
reimplements exactly those three primitives as ``capture_pane()`` polling loops,
each with a hard timeout so nothing hangs.

``TmuxSessionDriver`` duck-types on the session (any object with ``send_keys`` and
``capture_pane``), so it's unit-testable with a fake — no Docker, no tmux.
"""
from __future__ import annotations

import re
import time
from typing import List, Optional, Sequence, Tuple


class TmuxSessionDriver:
    """Perceive/act/wait wrapper around a Terminal-Bench ``TmuxSession``.

    Args:
        session: the TB session (needs ``send_keys`` + ``capture_pane``; uses
            ``get_incremental_output`` when present).
        poll_ms: poll interval for the wait loops.
        clock: injectable ``() -> float`` monotonic clock (tests use a fake to
            avoid real sleeps); defaults to :func:`time.monotonic`.
        sleep: injectable sleep (tests pass a no-op); defaults to :func:`time.sleep`.
    """

    def __init__(self, session, poll_ms: int = 100, clock=None, sleep=None):
        self.session = session
        self.poll_ms = poll_ms
        self._clock = clock or time.monotonic
        self._sleep = sleep if sleep is not None else time.sleep

    # -- perceive ----------------------------------------------------------
    def snapshot(self) -> str:
        """Current rendered pane text (perception = capture_pane)."""
        return self.session.capture_pane()

    # -- act ---------------------------------------------------------------
    def send_keys(self, keys, block: bool = False,
                  max_timeout_sec: float = 180.0) -> None:
        """Send key tokens/strings to the pane (thin pass-through to the session)."""
        k = keys if isinstance(keys, (list, tuple)) else [keys]
        self.session.send_keys(list(k), block=block, max_timeout_sec=max_timeout_sec)

    def send_line(self, text: str, block: bool = False) -> None:
        """Type ``text`` then Enter."""
        self.session.send_keys([text, "Enter"], block=block)

    # -- wait --------------------------------------------------------------
    def _poll_sleep(self) -> None:
        # Always sleep a tiny positive amount even at poll_ms=0: with a real clock
        # this is negligible, but it guarantees an injected/fake monotonic clock
        # (which only advances on sleep) still progresses toward the deadline —
        # otherwise a poll_ms=0 wait that never matches would spin forever in tests.
        self._sleep(max(self.poll_ms / 1000.0, 0.001))

    def wait_stable(self, quiet_polls: int = 2, timeout_sec: float = 10.0,
                    min_wait_sec: float = 0.3) -> bool:
        """Block until ``capture_pane()`` is unchanged for ``quiet_polls`` reads.

        Dwell-based settle, the tmux equivalent of ``smartcli_core.wait_until_stable``
        — including its ``min_wait`` floor. ``min_wait_sec`` is the crucial guard
        against the *stale-screen race*: right after ``send_line`` the shell instantly
        echoes the typed command (a static line), which would otherwise satisfy the
        dwell counter before a slow command (network / compile / ``sleep``) has emitted
        any output — declaring "stable" on the pre-output screen. So stability is not
        accepted until at least ``min_wait_sec`` has elapsed. Returns True once the
        screen holds still (past the floor), False on timeout.
        """
        start = self._clock()
        deadline = start + timeout_sec
        last = object()  # sentinel != any string
        stable = 0
        while True:
            cur = self.snapshot()
            if cur == last:
                stable += 1
                if stable >= quiet_polls and (self._clock() - start) >= min_wait_sec:
                    return True
            else:
                stable = 0
                last = cur
            if self._clock() >= deadline:
                return False
            self._poll_sleep()

    def wait_for(self, pattern: str, timeout_sec: float = 10.0,
                 flags: int = 0) -> Tuple[bool, str]:
        """Block until ``pattern`` appears in the pane. Returns (matched, screen)."""
        rx = re.compile(pattern, flags)
        deadline = self._clock() + timeout_sec
        while True:
            screen = self.snapshot()
            if rx.search(screen):
                return True, screen
            if self._clock() >= deadline:
                return False, screen
            self._poll_sleep()

    def wait_any(self, patterns: Sequence[str], timeout_sec: float = 10.0,
                 flags: int = 0) -> Tuple[int, str]:
        """Block until ANY of ``patterns`` appears (earliest-in-list wins a tie).

        Mirrors ``smartcli_core.wait_any``: returns (index, screen), index -1 on
        timeout, empty list short-circuits to (-1, screen).
        """
        rxs = [re.compile(p, flags) for p in patterns]
        if not rxs:
            return -1, self.snapshot()
        deadline = self._clock() + timeout_sec
        while True:
            screen = self.snapshot()
            for i, rx in enumerate(rxs):
                if rx.search(screen):
                    return i, screen
            if self._clock() >= deadline:
                return -1, screen
            self._poll_sleep()

    def wait_change(self, baseline: Optional[str] = None,
                    timeout_sec: float = 10.0) -> Tuple[bool, str]:
        """Block until the pane differs from ``baseline`` (default: the screen now).

        The "did my action land?" primitive. Returns (changed, screen); changed is
        False on timeout. Baseline is captured WITHOUT advancing first, so the very
        change we're waiting for can't be folded into the baseline.
        """
        if baseline is None:
            baseline = self.snapshot()
        deadline = self._clock() + timeout_sec
        while True:
            cur = self.snapshot()
            if cur != baseline:
                return True, cur
            if self._clock() >= deadline:
                return False, cur
            self._poll_sleep()
