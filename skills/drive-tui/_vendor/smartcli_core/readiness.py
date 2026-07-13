"""Readiness synchronisation for driving an interactive PTY program.

Three independent signals, combined so the agent never fires input into a
program that isn't ready and never hangs on an animation:

* **Quiescence** -- no bytes arriving (transport level).
* **Screen stability** -- the pyte content hash stops changing (semantic level,
  survives chunked/bursty reads). Cursor-only and attribute-only changes are
  excluded from the hash upstream in :meth:`ScreenModel.content_hash`.
* **Marker match** -- an expected regex appears (strongest signal).

Every wait has a hard ``max_wait`` ceiling so spinners/progress bars return the
last screen instead of hanging.

The functions take plain callables (``read_fn`` to pump bytes, ``get_screen_hash_fn``
to sample stability, ``get_snapshot_fn`` to produce a result) so they stay
decoupled from the session/backend concrete types.
"""

from __future__ import annotations

import re
import time
from typing import Callable, Optional, Tuple

# Callable aliases (documentation only)
ReadFn = Callable[[], bytes]      # pump: read+feed one batch, return bytes read
HashFn = Callable[[], int]        # sample the cursor-excluded content hash
TextFn = Callable[[], str]        # current rendered screen text (for regex)


def _ms(seconds: float) -> float:
    return seconds


def wait_until_stable(
    read_fn: ReadFn,
    get_screen_hash_fn: HashFn,
    quiet_ms: int = 200,
    poll_ms: int = 30,
    max_wait_ms: int = 8000,
    grace_ms: int = 40,
    min_wait_ms: int = 0,
    blank_hash: Optional[int] = None,
) -> bool:
    """Pump reads until the screen hash is unchanged for ``quiet_ms``.

    The stable timer resets on *either* new bytes arriving *or* the hash
    changing; quiet time accumulates only when both are absent. After stability
    is declared a short ``grace`` sleep absorbs a late flush, then one final
    drain re-checks; if the flush changed the screen, the wait resumes.

    Args:
        read_fn: called each poll to read+feed a batch; returns bytes read.
        get_screen_hash_fn: returns the current cursor-excluded content hash.
        quiet_ms: continuous no-change duration required to declare stable.
        poll_ms: sleep between polls when idle.
        max_wait_ms: hard ceiling; returns ``False`` if reached.
        grace_ms: final settle sleep after stability, before returning.
        min_wait_ms: minimum elapsed time before stability may be declared
            (guards the stale-screen race right after sending input).

    Returns:
        ``True`` if the screen settled, ``False`` on timeout.
    """
    poll = poll_ms / 1000.0
    quiet = quiet_ms / 1000.0
    grace = grace_ms / 1000.0
    min_wait = min_wait_ms / 1000.0

    start = time.monotonic()
    deadline = start + (max_wait_ms / 1000.0)
    last_hash: Optional[int] = None
    stable_since: Optional[float] = None
    # Readiness gate: never declare stable on a never-painted BLANK screen. Only
    # engages when the caller passes ``blank_hash`` (the construct-time all-blank
    # baseline) AND no output has been seen this wait AND the screen still equals
    # that baseline. Default (blank_hash=None) is byte-for-byte the old behavior,
    # so an already-drawn screen that is genuinely static still settles.
    seen_any = False

    while True:
        now = time.monotonic()
        data = read_fn()
        if data:
            seen_any = True
        h = get_screen_hash_fn()
        elapsed = now - start
        blank = (not seen_any and blank_hash is not None and h == blank_hash)

        if not data and h == last_hash:
            if stable_since is None:
                stable_since = now
            elif (now - stable_since) >= quiet and elapsed >= min_wait and not blank:
                if grace > 0:
                    time.sleep(grace)
                tail = read_fn()
                if tail:
                    # late flush: resume waiting
                    seen_any = True
                    stable_since = None
                    last_hash = get_screen_hash_fn()
                    continue
                return True
        else:
            stable_since = None
            last_hash = h

        if now >= deadline:
            return False
        time.sleep(poll)


def wait_for_regex(
    read_fn: ReadFn,
    get_text_fn: TextFn,
    get_snapshot_fn: Callable[[], object],
    pattern: str,
    timeout_ms: int = 10000,
    poll_ms: int = 30,
    min_wait_ms: int = 0,
    flags: int = 0,
) -> Tuple[bool, object]:
    """Pump reads until ``pattern`` matches the rendered screen, or timeout.

    Args:
        read_fn: called each poll to read+feed a batch.
        get_text_fn: returns the current screen text searched by the regex.
        get_snapshot_fn: builds the :class:`Snapshot` returned to the caller.
        pattern: regular expression searched against the whole screen text.
        timeout_ms: hard ceiling.
        poll_ms: sleep between polls when idle.
        min_wait_ms: ignore matches before this much time has elapsed (guards
            against matching a stale prior prompt).
        flags: extra ``re`` flags (``re.I`` etc.).

    Returns:
        ``(matched, snapshot)`` -- ``snapshot`` is always the current screen,
        even on timeout, so the agent can act on the last state.
    """
    rx = re.compile(pattern, flags)
    poll = poll_ms / 1000.0
    min_wait = min_wait_ms / 1000.0
    start = time.monotonic()
    deadline = start + (timeout_ms / 1000.0)

    while True:
        now = time.monotonic()
        read_fn()
        elapsed = now - start
        if elapsed >= min_wait and rx.search(get_text_fn()):
            return True, get_snapshot_fn()
        if now >= deadline:
            return False, get_snapshot_fn()
        time.sleep(poll)


def wait_ready(
    read_fn: ReadFn,
    get_screen_hash_fn: HashFn,
    get_text_fn: TextFn,
    get_snapshot_fn: Callable[[], object],
    marker: Optional[str] = None,
    quiet_ms: int = 200,
    poll_ms: int = 30,
    max_wait_ms: int = 10000,
    min_wait_ms: int = 50,
    grace_ms: int = 40,
    flags: int = 0,
    blank_hash: Optional[int] = None,
) -> Tuple[str, object]:
    """Unified wait: satisfy on ``marker`` OR screen stability, capped by max_wait.

    A single loop races the marker (if given) against stability so callers get
    the earliest safe moment. ``min_wait_ms`` guards the stale-screen race after
    sending input.

    Returns:
        ``(reason, snapshot)`` where ``reason`` is ``"MARKER"``, ``"STABLE"`` or
        ``"TIMEOUT"``. The snapshot is always the current screen.
    """
    rx = re.compile(marker, flags) if marker else None
    poll = poll_ms / 1000.0
    quiet = quiet_ms / 1000.0
    grace = grace_ms / 1000.0
    min_wait = min_wait_ms / 1000.0

    start = time.monotonic()
    deadline = start + (max_wait_ms / 1000.0)
    last_hash: Optional[int] = None
    stable_since: Optional[float] = None
    # Readiness gate (see wait_until_stable): a marker match is never gated —
    # only the stability branch refuses to fire on a never-painted blank screen
    # when the caller supplies the blank baseline. Default None = old behavior.
    seen_any = False

    while True:
        now = time.monotonic()
        data = read_fn()
        if data:
            seen_any = True
        elapsed = now - start

        # 1) marker wins immediately (respect min_wait)
        if rx is not None and elapsed >= min_wait and rx.search(get_text_fn()):
            return "MARKER", get_snapshot_fn()

        # 2) stability
        h = get_screen_hash_fn()
        blank = (not seen_any and blank_hash is not None and h == blank_hash)
        if not data and h == last_hash:
            if stable_since is None:
                stable_since = now
            elif (now - stable_since) >= quiet and elapsed >= min_wait and not blank:
                if grace > 0:
                    time.sleep(grace)
                tail = read_fn()
                if tail:
                    seen_any = True
                    stable_since = None
                    last_hash = get_screen_hash_fn()
                    continue
                return "STABLE", get_snapshot_fn()
        else:
            stable_since = None
            last_hash = h

        if now >= deadline:
            return "TIMEOUT", get_snapshot_fn()
        time.sleep(poll)
