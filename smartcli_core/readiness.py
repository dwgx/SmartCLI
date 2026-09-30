"""Readiness synchronisation for driving an interactive PTY program.

Independent signals, combined so the agent never fires input into a program that
isn't ready, never mistakes an old screen for a new one, and never hangs on an
animation:

* **Quiescence** -- no bytes arriving (transport level).
* **Screen stability** -- the pyte content hash stops changing (semantic level,
  survives chunked/bursty reads). Cursor-only and attribute-only changes are
  excluded from the hash upstream in :meth:`ScreenModel.content_hash`.
* **Marker match** -- an expected regex appears (strongest signal).
* **Child death** -- the program under test is gone. Not one of the wait
  conditions, but a first-class *outcome*: without it a crashed child makes
  every wait below sit out its whole ceiling, and on a ``wait_ready`` with a
  long ``max_wait_ms`` that is the difference between one second and thirty.
  It is opt-in (``alive_fn``), because only the caller knows whether the
  child dying is a result or an expected part of the scenario.

* **Revision baseline** -- "something changed since I last looked". Opt-in
  (``changed_since``), and the STATE-based replacement for the ``min_wait_ms``
  millisecond guess: while the caller's anchor is still closed the wait reports
  no success at all, so a screen that was already showing the target cannot be
  mistaken for one that has just reached it. The gate suppresses success only --
  never the ``max_wait`` ceiling and never the child-death outcome.

Every wait has a hard ``max_wait`` ceiling so spinners/progress bars return the
last screen instead of hanging.

The functions take plain callables (``read_fn`` to pump bytes, ``get_screen_hash_fn``
to sample stability, ``get_snapshot_fn`` to produce a result) so they stay
decoupled from the session/backend concrete types.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from typing import Optional

# Callable aliases (documentation only)
ReadFn = Callable[[], bytes]      # pump: read+feed one batch, return bytes read
HashFn = Callable[[], int]        # sample the cursor-excluded content hash
TextFn = Callable[[], str]        # current rendered screen text (for regex)


def _ms(seconds: float) -> float:
    return seconds


#: Optional callback invoked in the gap between polls of every wait primitive.
#:
#: WHY THIS EXISTS: a wait blocks for as long as its timeout, and the drive-tui
#: daemon has exactly one thread allowed to touch a session (``PtySession`` is not
#: thread-safe — ``visual_hash()`` clears ``screen.dirty`` as a side effect,
#: ``pump()`` is read-modify-write, ``resize()`` mutates four fields in sequence).
#: Without a hook, a 60s ``wait-regex`` makes an unrelated ``snapshot`` on another
#: connection wait 60s behind it. The callback runs ON THE WAITING THREAD, in the
#: idle gap, so that single-threaded-session invariant is preserved rather than
#: traded away.
#:
#: Contract: called with no arguments, return value ignored, and it MUST be quick —
#: it delays the next poll by however long it runs. Exceptions propagate, because a
#: silently swallowed callback error is worse than a loud one. Default ``None``
#: keeps every existing caller byte-identical in behaviour.
#: PEP 604 union, matching the rest of this package (the 3.10 floor allows it, and
#: `from __future__ import annotations` above makes it safe in annotations).
PollHook = Callable[[], None] | None

#: Optional liveness predicate: returns ``True`` while the child is still
#: running. Supplied to every wait primitive; when it reports ``False`` the wait
#: returns promptly instead of running out its ceiling.
#:
#: WHY THIS EXISTS: "the screen stopped changing" and "the program died" are
#: different facts, and an agent acting on the wrong one does the wrong thing.
#: ``pexpect`` has ``searcher_re``'s ``EOF`` sentinel and Microsoft's
#: ``tui-test`` has ``session_stopped()``; a bare deadline loop has neither, so
#: a child that crashes on the first input costs the agent the entire timeout.
#:
#: Contract: called with no arguments, at most once per poll, AFTER that poll's
#: read and content evaluation and BEFORE the deadline check. Exceptions
#: propagate, for the same reason ``on_poll``'s do. Default ``None`` performs
#: no call at all and keeps every existing caller byte-for-byte unchanged --
#: the ``is not None`` test is the only thing added to the hot loop.
#: PEP 604 union, matching :data:`PollHook` above.
AliveFn = Callable[[], bool] | None

#: Optional "has the screen changed since my anchor?" predicate: returns
#: ``True`` once the screen has moved past the state the caller last observed.
#:
#: WHY THIS EXISTS: every other readiness knob is a GUESS about time -- "wait at
#: least 50 ms in case the screen is stale", "go quiet for 200 ms". The guess
#: cannot tell two situations apart: the program is still working, or it
#: finished before the wait began and the answer is already on the screen.
#: Both look identical from inside the loop, and the second one is reported as
#: success. ``agent-tty`` (coder) solves this with ``--after-seq``: a wait
#: BASELINE rather than a wait DURATION.
#:
#: HOW IT COMPOSES: the predicate gates SUCCESS only. While it reports
#: ``False``, every success branch below is skipped, so the wait cannot report
#: ``True``/``"STABLE"``/``"MARKER"``/a match index on the pre-anchor screen. It
#: never gates the other two exits: the deadline still returns the ordinary
#: timeout when the screen simply never changes, and ``alive_fn`` still wins
#: the instant it reports the child gone -- a dead child is a fact about the
#: world, not a screen that failed to change. That asymmetry is deliberate: the
#: anchor exists to stop a STALE screen being called a NEW one, and there is no
#: reading under which a dead child becomes interesting again just because
#: nothing was drawn.
#:
#: Contract: called with no arguments, at most once per poll, BEFORE this
#: poll's success branches are evaluated. Exceptions propagate, for the same
#: reason ``on_poll``'s and ``alive_fn``'s do. Default ``None`` performs no call
#: at all and keeps every existing caller byte-for-byte unchanged.
#: PEP 604 union, matching :data:`PollHook` and :data:`AliveFn` above.
ChangedSince = Callable[[], bool] | None


class Exited:
    """The "the child is gone" wait outcome. Falsy, comparable only to itself.

    WHY A SINGLETON AND NOT ``False``: ``False``/``-1``/``"TIMEOUT"`` all mean
    "I waited and the condition never happened". Reporting a dead child that
    way loses the one fact the caller needs, and it is the fact that decides
    what to do next. This is falsy, so ``if sess.wait_stable():`` still reads
    as "the screen settled" for any caller that has not opted into the
    distinction -- but ``result is readiness.EXITED`` is unambiguous, and
    ``result == -1`` is ``False``, so an opted-in caller cannot confuse it
    with a timeout.

    Only ever returned when an ``alive_fn`` was supplied; the default path
    cannot produce it.
    """

    __slots__ = ()

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "EXITED"

    def __eq__(self, other: object) -> bool:
        return other is self

    def __hash__(self) -> int:
        return hash(Exited)


#: The child-death outcome, shared by every wait primitive.
EXITED = Exited()


#: The ``reason`` string :func:`wait_ready` returns when ``alive_fn`` reports
#: the child gone. A string, to match that function's existing
#: ``"MARKER"``/``"STABLE"``/``"TIMEOUT"`` vocabulary -- but a NEW member of it,
#: because ``"TIMEOUT"`` asserts the program is still running and merely failed
#: to get somewhere, which is the opposite advice. Callers that switch on the
#: reason keep working unchanged: an unknown value falls through their default
#: arm, and only a caller that passes ``alive_fn`` can ever receive this one.
EXITED_REASON = "EXITED"


def _io_blocks_stability(io_block: dict | None) -> bool:
    """Can this observation NOT be called complete yet? (A04-S2)

    ``local_cut`` is the transport's own verdict: anything other than ``drained``
    means the runtime knows it has not consumed everything it received
    (``budget_limited``), does not know (``unknown``), or has a transport error.
    Rounding those to "quiet" is the failure this gate exists to prevent: a
    budget-shaped read that stops mid-stream must not look like a stable screen.

    ``None``/absent fields never block by themselves -- a missing count is not
    evidence of data, and blocking on it would turn every wait into a timeout.
    """
    if not io_block:
        return False
    if io_block.get("local_cut") not in ("drained", None):
        return True
    pending = io_block.get("pending") or {}
    if pending.get("known_payload_bytes"):      # a positive count is real data
        return True
    if pending.get("readable_now") is True:
        return True
    if pending.get("parser_incomplete") is True:
        return True
    if pending.get("reply_bytes"):              # a device reply still unwritten
        return True
    return False


def _io_epoch(io_block: dict | None):
    """Monotone progress marker: bytes fed within this generation.

    A poll hook (or an interleaved fast request) can advance the model without
    changing the visible hash -- a CPR reply, a cursor-only repaint. Comparing
    this value across polls invalidates a quiet candidate that was measured
    before that progress, which is what the old ``data``-only reset missed.
    """
    if not io_block:
        return None
    return io_block.get("fed_offset")


def _anchor_open(changed_since: ChangedSince) -> bool:
    """Is this wait's revision anchor satisfied (or was none asked for)?

    One place decides, so all four primitives agree on what a closed anchor
    means: the success branches are unreachable, the deadline and the
    child-death check are not. Returns ``True`` when no anchor was supplied --
    the default -- so an unanchored wait's hot loop costs exactly one
    ``is not None`` test and no call, the same bargain :data:`AliveFn` makes.
    """
    return changed_since is None or changed_since()


def wait_until_stable(
    read_fn: ReadFn,
    get_screen_hash_fn: HashFn,
    quiet_ms: int = 200,
    poll_ms: int = 30,
    max_wait_ms: int = 8000,
    grace_ms: int = 40,
    min_wait_ms: int = 0,
    blank_hash: int | None = None,
    on_poll: PollHook = None,
    io_fn: Optional[Callable[[], dict]] = None,
    alive_fn: AliveFn = None,
    changed_since: ChangedSince = None,
) -> bool | Exited:
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

        alive_fn: optional liveness predicate. When it reports the child gone
            the wait returns :data:`EXITED` promptly instead of running out
            ``max_wait_ms``. See :data:`AliveFn`.

        changed_since: optional "has the screen changed since my anchor?"
            predicate. While it reports ``False`` this wait cannot return
            ``True`` -- it will not call a pre-anchor screen settled. The
            deadline still applies, so a wait that is anchored and never sees a
            change returns ``False`` at ``max_wait_ms``. See
            :data:`ChangedSince`.

    Returns:
        ``True`` if the screen settled, ``False`` on timeout, or
        :data:`EXITED` if ``alive_fn`` reported the child gone. ``False`` and
        ``EXITED`` are deliberately distinct: one says the program went quiet,
        the other says it is no longer running, and a caller that acts on the
        wrong one either re-sends input into a dead program or waits again for
        a prompt that can never arrive.
    """
    poll = poll_ms / 1000.0
    quiet = quiet_ms / 1000.0
    grace = grace_ms / 1000.0
    min_wait = min_wait_ms / 1000.0

    start = time.monotonic()
    deadline = start + (max_wait_ms / 1000.0)
    last_hash: int | None = None
    stable_since: float | None = None
    # Readiness gate: never declare stable on a never-painted BLANK screen. Only
    # engages when the caller passes ``blank_hash`` (the construct-time all-blank
    # baseline) AND no output has been seen this wait AND the screen still equals
    # that baseline. Default (blank_hash=None) is byte-for-byte the old behavior,
    # so an already-drawn screen that is genuinely static still settles.
    seen_any = False
    # A04-S2: when the caller supplies the runtime's io block, a quiet window only
    # counts while the runtime is genuinely drained. ``last_epoch`` invalidates a
    # candidate that was measured before any progress the poll hook made.
    last_epoch = None

    while True:
        now = time.monotonic()
        data = read_fn()
        if data:
            seen_any = True
        io_block = io_fn() if io_fn is not None else None
        blocked = _io_blocks_stability(io_block)
        epoch = _io_epoch(io_block)
        progressed = bool(data) or (epoch is not None and last_epoch is not None
                                    and epoch != last_epoch)
        last_epoch = epoch
        h = get_screen_hash_fn()
        elapsed = now - start
        blank = (not seen_any and blank_hash is not None and h == blank_hash)
        # A closed anchor disqualifies the screen from being called SETTLED, so
        # it takes the same branch as a change: the quiet timer restarts. That is
        # what makes "changed since I looked" mean something -- once the anchor
        # opens, the quiet window still has to be served by the post-change
        # screen, not by whatever stillness preceded it.
        anchored = _anchor_open(changed_since)

        if anchored and not progressed and h == last_hash and not blocked:
            if stable_since is None:
                stable_since = now
            elif (now - stable_since) >= quiet and elapsed >= min_wait and not blank:
                if grace > 0:
                    time.sleep(grace)
                tail = read_fn()
                io_after = io_fn() if io_fn is not None else None
                if tail or _io_blocks_stability(io_after):
                    # late flush, or work the grace window uncovered: resume waiting
                    seen_any = seen_any or bool(tail)
                    stable_since = None
                    last_hash = get_screen_hash_fn()
                    last_epoch = _io_epoch(io_after)
                    continue
                return True
        else:
            stable_since = None
            last_hash = h

        # Child death is checked AFTER this poll's content evaluation and
        # BEFORE the deadline, so on a poll where both the settle condition and
        # the death are observable the settle wins (see the race note in
        # wait_ready); the two are otherwise indistinguishable from outside.
        if alive_fn is not None and not alive_fn():
            return EXITED

        if now >= deadline:
            return False
        if on_poll is not None:
            on_poll()
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
    on_poll: PollHook = None,
    alive_fn: AliveFn = None,
    changed_since: ChangedSince = None,
) -> tuple[bool | Exited, object]:
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
        alive_fn: optional liveness predicate; see :data:`AliveFn`.
        changed_since: optional "has the screen changed since my anchor?"
            predicate; see :data:`ChangedSince`. While closed, a match that was
            already on the pre-anchor screen is not reported as one.

    Returns:
        ``(matched, snapshot)`` -- ``matched`` is ``True`` on a match, ``False``
        on timeout, and :data:`EXITED` when ``alive_fn`` reported the child gone
        before a match. ``snapshot`` is always the current screen, even on
        timeout, so the agent can act on the last state.
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
        # Race rule, uniform across every wait: the CONTENT condition is
        # evaluated first, so a match that becomes visible on the same poll the
        # child dies is still a match (see wait_ready for the full argument).
        # "Exited after the marker matched" is therefore reported as the
        # marker; only "exited before" is EXITED.
        anchored = _anchor_open(changed_since)
        if anchored and elapsed >= min_wait and rx.search(get_text_fn()):
            return True, get_snapshot_fn()
        if alive_fn is not None and not alive_fn():
            return EXITED, get_snapshot_fn()
        if now >= deadline:
            return False, get_snapshot_fn()
        if on_poll is not None:
            on_poll()
        time.sleep(poll)


def wait_any(
    read_fn: ReadFn,
    get_text_fn: TextFn,
    get_snapshot_fn: Callable[[], object],
    patterns: Sequence[str],
    timeout_ms: int = 10000,
    poll_ms: int = 30,
    min_wait_ms: int = 0,
    flags: int = 0,
    on_poll: PollHook = None,
    alive_fn: AliveFn = None,
    changed_since: ChangedSince = None,
) -> tuple[int | Exited, object]:
    """Pump reads until ANY of ``patterns`` matches the screen, or timeout.

    The pexpect ``expect([...])`` analogue: race several possible outcomes
    (prompt vs error vs EOF banner) and report WHICH one appeared first. Patterns
    are scanned **in list order** each poll, so when two would match on the same
    poll the earliest in the list wins (deterministic, documented) — order the
    list most-specific-first if that matters.

    Args:
        read_fn: called each poll to read+feed a batch.
        get_text_fn: returns the current screen text searched by the regexes.
        get_snapshot_fn: builds the :class:`Snapshot` returned to the caller.
        patterns: regexes searched against the whole screen text, in priority order.
        timeout_ms: hard ceiling.
        poll_ms: sleep between polls when idle.
        min_wait_ms: ignore matches before this much time has elapsed (guards
            against matching a stale prior prompt right after sending input).
        alive_fn: optional liveness predicate; see :data:`AliveFn`.
        flags: extra ``re`` flags (``re.I`` etc.) applied to every pattern.
        changed_since: optional "has the screen changed since my anchor?"
            predicate; see :data:`ChangedSince`. While closed, a pattern that
            was already matching the pre-anchor screen is not reported.

    Returns:
        ``(index, snapshot)`` — ``index`` is the 0-based position in ``patterns``
        of the pattern that matched, ``-1`` on timeout, or :data:`EXITED` when
        ``alive_fn`` reported the child gone before any pattern matched. An empty
        ``patterns`` list can never match, so it returns ``(-1, snapshot)``
        immediately (one pump, no spin to the deadline). The snapshot is always
        the current screen so the caller can act on the last state either way.
    """
    rxs = [re.compile(p, flags) for p in patterns]
    if not rxs:
        # Nothing to match — pump once (so the snapshot is fresh) and report the
        # timeout sentinel now instead of spinning the whole timeout window.
        read_fn()
        return -1, get_snapshot_fn()
    poll = poll_ms / 1000.0
    min_wait = min_wait_ms / 1000.0
    start = time.monotonic()
    deadline = start + (timeout_ms / 1000.0)

    while True:
        now = time.monotonic()
        read_fn()
        elapsed = now - start
        anchored = _anchor_open(changed_since)
        if anchored and elapsed >= min_wait:
            text = get_text_fn()
            for i, rx in enumerate(rxs):
                if rx.search(text):
                    return i, get_snapshot_fn()
        # Same race rule as wait_for_regex: the patterns are scanned FIRST, so
        # a match that becomes visible on the poll the child dies on is still
        # reported as that match. Only "died before anything matched" is EXITED.
        if alive_fn is not None and not alive_fn():
            return EXITED, get_snapshot_fn()
        if now >= deadline:
            return -1, get_snapshot_fn()
        if on_poll is not None:
            on_poll()
        time.sleep(poll)


def wait_ready(
    read_fn: ReadFn,
    get_screen_hash_fn: HashFn,
    get_text_fn: TextFn,
    get_snapshot_fn: Callable[[], object],
    marker: str | None = None,
    quiet_ms: int = 200,
    poll_ms: int = 30,
    max_wait_ms: int = 10000,
    min_wait_ms: int = 50,
    grace_ms: int = 40,
    flags: int = 0,
    blank_hash: int | None = None,
    on_poll: PollHook = None,
    io_fn: Optional[Callable[[], dict]] = None,
    alive_fn: AliveFn = None,
    changed_since: ChangedSince = None,
) -> tuple[str, object]:
    """Unified wait: satisfy on ``marker`` OR screen stability, capped by max_wait.

    A single loop races the marker (if given) against stability so callers get
    the earliest safe moment. ``min_wait_ms`` guards the stale-screen race after
    sending input.

    THE RACE BETWEEN "the marker matched" AND "the child died": both are
    evaluated on the same poll, and the CONTENT condition is evaluated FIRST,
    so a marker that becomes visible on the very poll the child dies on is
    reported as ``"MARKER"``. The reasoning: the marker's whole purpose is to
    tell the agent the program reached a known state -- most often by printing
    it as its last act before exiting (a usage banner, a goodbye, a traceback
    header). Reporting ``"EXITED"`` there would throw away the one piece of
    information the agent sent the wait for. "Exited after the marker matched"
    is therefore indistinguishable from "matched while alive", and only "exited
    before anything matched" is ``EXITED_REASON``. That direction also cannot
    hide a real condition, since the content check is a pure read of the screen
    that already contains the child's final output.

    Args:
        alive_fn: optional liveness predicate; when it reports the child gone
            the wait returns ``EXITED_REASON`` instead of sitting out
            ``max_wait_ms``. See :data:`AliveFn`.

        changed_since: optional "has the screen changed since my anchor?"
            predicate; see :data:`ChangedSince`. While it reports ``False``
            BOTH success branches are unreachable -- neither ``"MARKER"`` nor
            ``"STABLE"`` can be reported against the pre-anchor screen. The
            anchor composes with the marker/death race exactly as ``alive_fn``
            does: it is checked first, so the first poll on which the screen both
            moves and the marker is visible still reports ``"MARKER"``.

    Returns:
        ``(reason, snapshot)`` where ``reason`` is ``"MARKER"``, ``"STABLE"``,
        ``"TIMEOUT"``, or ``EXITED_REASON`` (``"EXITED"``, and only when
        ``alive_fn`` was supplied). The snapshot is always the current screen.
        ``TIMEOUT`` means "the program is still running and never got there";
        ``EXITED`` means "it is gone and the answer will never arrive".
    """
    rx = re.compile(marker, flags) if marker else None
    poll = poll_ms / 1000.0
    quiet = quiet_ms / 1000.0
    grace = grace_ms / 1000.0
    min_wait = min_wait_ms / 1000.0

    start = time.monotonic()
    deadline = start + (max_wait_ms / 1000.0)
    last_hash: int | None = None
    stable_since: float | None = None
    # Readiness gate (see wait_until_stable): a marker match is never gated —
    # only the stability branch refuses to fire on a never-painted blank screen
    # when the caller supplies the blank baseline. Default None = old behavior.
    seen_any = False
    # A04-S2: STABLE additionally requires that the runtime is actually drained;
    # see wait_until_stable for the reasoning. A marker match stays ungated.
    last_epoch = None

    while True:
        now = time.monotonic()
        data = read_fn()
        if data:
            seen_any = True
        io_block = io_fn() if io_fn is not None else None
        blocked = _io_blocks_stability(io_block)
        epoch = _io_epoch(io_block)
        progressed = bool(data) or (epoch is not None and last_epoch is not None
                                    and epoch != last_epoch)
        last_epoch = epoch
        elapsed = now - start
        # A closed anchor gates BOTH success branches, for the same reason
        # wait_until_stable restarts its quiet timer: stillness before the
        # change the agent is waiting for is not readiness.
        anchored = _anchor_open(changed_since)

        # 1) marker wins immediately (respect min_wait)
        if rx is not None and anchored and elapsed >= min_wait and rx.search(get_text_fn()):
            return "MARKER", get_snapshot_fn()

        # 2) stability
        h = get_screen_hash_fn()
        blank = (not seen_any and blank_hash is not None and h == blank_hash)
        if anchored and not progressed and h == last_hash and not blocked:
            if stable_since is None:
                stable_since = now
            elif (now - stable_since) >= quiet and elapsed >= min_wait and not blank:
                if grace > 0:
                    time.sleep(grace)
                tail = read_fn()
                io_after = io_fn() if io_fn is not None else None
                if tail or _io_blocks_stability(io_after):
                    seen_any = seen_any or bool(tail)
                    stable_since = None
                    last_hash = get_screen_hash_fn()
                    last_epoch = _io_epoch(io_after)
                    continue
                return "STABLE", get_snapshot_fn()
        else:
            stable_since = None
            last_hash = h

        # Third branch of the race, and the only one that can fire without the
        # screen changing: the child is gone, so MARKER and STABLE will never
        # arrive on their own. Checked after both, per the race note above.
        if alive_fn is not None and not alive_fn():
            return EXITED_REASON, get_snapshot_fn()

        if now >= deadline:
            return "TIMEOUT", get_snapshot_fn()
        if on_poll is not None:
            on_poll()
        time.sleep(poll)
