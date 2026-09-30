"""Opt-in session event log -- a JSON Lines record of what an agent DID to a PTY.

WHY THIS EXISTS
---------------
A driving session fails in the present tense. The program hung, the wait timed
out, the keystroke went somewhere else, the child died on the third prompt -- and
afterwards the evidence is whatever the agent remembered writing down. The bytes
on the wire are gone, and ``PtySession`` keeps only *current* state: a screen
model, an io ledger, a close protocol. Nothing in it answers "what did I ask for,
what came back, and how long did it take", which is exactly the question a
post-mortem asks.

This module is that missing record: one JSON object per line, appended as the
session acts, so a run can be read back -- or tailed while it is still running --
after a crash, a hang, or a session that ended in a state nobody can explain.

OFF BY DEFAULT, AND NOT A BASE CLASS
------------------------------------
Nothing here is wired into :class:`~smartcli_core.session.PtySession`. There is
no attribute to set on it, no import it performs, no branch in its hot loop. A
caller opts in by wrapping the session::

    from smartcli_core import PtySession
    from smartcli_core.sessionlog import JsonlFileSink, LoggedSession, SessionLog

    with JsonlFileSink("run.jsonl") as sink:
        log = SessionLog("agent-42", sink)
        sess = LoggedSession(PtySession(), log)
        sess.start("python")
        sess.send_line("print(6*7)")
        reason, snap = sess.wait_ready(marker=r">>> ", alive_fn=sess.session.is_alive)


The example deliberately passes the *session's* ``is_alive``, not the wrapper's:
``sess.is_alive`` records a ``session.alive`` event, so using it as a wait's
``alive_fn`` writes one event per poll.

``LoggedSession`` is a transparent delegating wrapper, not a subclass, so the
runtime keeps exactly one class to maintain and the log can never change a wait's
behaviour -- it only observes the call and its return value. Every method it
defines forwards verbatim; everything else falls through ``__getattr__`` to the
real session.

THE SHAPE: JSON LINES, NOT A FORMAT OF OUR OWN
----------------------------------------------
One event per line, ``\\n``-terminated, UTF-8, from https://jsonlines.org. That is
the only common log shape that is simultaneously (a) streamable -- ``tail -f`` a
live session, (b) crash-tolerant -- a process killed mid-write leaves a truncated
final line, which :func:`read_events` skips instead of refusing the file, and
(c) greppable, which is how anyone actually reads a log. Every record carries a
fixed envelope so a consumer can route on it without knowing the payload::

    {"schema":"smartcli.session-log","schema_version":1,"seq":7,"ts":"...",
     "session_id":"agent-42","name":"input.send_line","attrs":{...}}

``name`` is ``<category>.<verb>`` and the verbs are the ones the CLI/MCP surface
already exposes (``start``, ``send_text``, ``send_keys``, ``send_line``,
``snapshot``, ``wait_ready``, ``wait_stable``, ``wait_for``, ``wait_any``,
``wait_change``, ``wait_visual_change``, ``resize``, ``alive``, ``close``), so
the log and the tool vocabulary cannot drift apart. Timestamps are RFC 3339 in
UTC with microsecond precision (``...Z``): sortable as strings, unambiguous about
the zone.

WHAT IS NOT WRITTEN DOWN BY DEFAULT
-----------------------------------
Terminal traffic carries credentials -- passwords typed at prompts, ``export
TOKEN=``, an ``ssh host@key``, argv with ``--token``. A log that records keystrokes
in clear text turns "the agent's run" into "the agent's secrets", and such a file
outlives the session by years. So text is recorded by DIGEST, not by content:
``text_chars`` (how much was typed) and ``text_sha256_16`` (a 64-bit SHA-256
prefix, stable across runs), which is enough to answer the forensic question that
actually matters -- "were these the same two keystrokes, or did a retry send
something different?" -- without writing the keystrokes down. Pass
``payloads="full"`` to opt into clear text when you know the traffic is not
sensitive; ``payloads="none"`` drops even the digest. The same policy governs
argv, screen text, error messages and anything else that can carry user data.

An exception message is the sharpest case of that rule, and the easiest to get
wrong: a spawn that fails raises the whole command line it was handed --
``RuntimeError('failed to spawn: ssh root@host --password hunter2')`` is a real
string a real backend produces -- so the message is scrubbed like any other
text. What stays verbatim is ``error_type``: a class name is not user data.

WHAT IS FREE
------------
The screen digest on a wait's event is read off the :class:`Snapshot` the wait
already built -- no extra hash, no second pass over the cell grid -- so
"what was on the screen when this gave up" is recorded by default. Only
``record_snapshots=True`` pays for ``to_text()``. ``pump()`` (the high-volume
read) is likewise opt-in via ``record_pumps=True``.

WHAT IT COSTS
-------------
One event is one dataclass, one small dict, one ``json.dumps`` and one sink
call. Measured on the dev box (CPython 3.14 / Windows, 20k events, 236 bytes per
event): **4.8 us** per event with no sink, **12.7 us** with a flushed JSON Lines
file; a wrapper call with the log disabled adds **0.2 us** over the bare session,
and a wrapper call that records one adds **~7 us**. The ordering is what
matters: one ``wait_*`` already costs milliseconds to seconds, so an event is
rounding error against the action it describes -- and an unwatched session pays
the 0.2 us, not the 7.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .readiness import EXITED, Exited

if TYPE_CHECKING:  # pragma: no cover - typing only; the log imports no PTY stack
    from .readiness import AliveFn, PollHook
    from .session import PtySession
    from .snapshot import Snapshot

#: Envelope discriminator + version. Bump ``SCHEMA_VERSION`` when the ENVELOPE
#: changes; add names/attrs without a bump, that is what the version is FOR.
SCHEMA = "smartcli.session-log"
SCHEMA_VERSION = 1

#: Payload policies for text that could carry user data (keystrokes, argv,
#: screen text, error messages).
PAYLOAD_NONE = "none"    # length only
PAYLOAD_HASH = "hash"    # length + a 64-bit SHA-256 prefix (the default)
PAYLOAD_FULL = "full"    # the text itself

#: Longest string kept verbatim in one attribute; longer values are cut and
#: marked with the number of dropped characters. A regex or a status bar has no
#: business being 400 KB in a log; a screen dump might, and this is where that
#: gets decided.
DEFAULT_MAX_ATTR_CHARS = 4096

#: Longest exception message kept, cut BEFORE the payload policy runs, so the
#: digest always identifies exactly the text ``payloads="full"`` would write.
MAX_ERROR_MESSAGE_CHARS = 200

#: How many events stay retrievable in memory. The sink (a file, a queue) is the
#: record of truth; this ring is a convenience for a post-mortem in the same
#: process, and it is bounded so a long session cannot grow without limit.
DEFAULT_MAX_EVENTS = 2048

Sink = Callable[[str], None]
Clock = Callable[[], float]

#: Hash prefix length for a text fingerprint: 16 hex chars = 64 bits. At log
#: scale (millions of events) the birthday collision probability is ~1e-7, and a
#: fingerprint is only ever used to compare two events, never to recover text.
_FINGERPRINT_HEX = 16


def rfc3339(epoch_seconds: float) -> str:
    """UTC RFC 3339 timestamp with microseconds and a literal ``Z``.

    Zone-explicit so a log is unambiguous after it crosses a timezone boundary,
    and lexicographically sortable so ``sort`` on the field is chronological.
    """
    stamp = datetime.fromtimestamp(epoch_seconds, timezone.utc).isoformat(
        timespec="microseconds")
    return stamp.replace("+00:00", "Z")


def text_fingerprint(text: str) -> str:
    """A short, stable, non-reversible id for a piece of text.

    Enough to answer "were these the same two inputs?" -- the question a
    post-mortem actually asks about a retried keystroke -- without writing the
    input down.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_FINGERPRINT_HEX]


def payload_attrs(key: str, text: str, policy: str) -> dict[str, Any]:
    """How one piece of text appears in an event, under ``policy``.

    Always ``<key>_chars``; with ``"hash"`` (the default) also
    ``<key>_sha256_16``; with ``"full"`` also ``<key>``; with ``"none"``
    nothing else. The length is metadata, not content, so it survives even
    the scrub-everything policy.

    The single funnel every text-bearing attribute goes through -- keystrokes,
    argv, screen text, queries, exception messages. One implementation is what
    makes the promise in the module docstring true rather than aspirational.
    """
    attrs: dict[str, Any] = {f"{key}_chars": len(text)}
    if policy == PAYLOAD_NONE:
        return attrs
    attrs[f"{key}_sha256_16"] = text_fingerprint(text)
    if policy == PAYLOAD_FULL:
        attrs[key] = text
    return attrs



def error_attrs(exc: BaseException, *, policy: str = PAYLOAD_HASH) -> dict[str, Any]:
    """How a raised exception appears in an event, under the payload policy.

    ``error_type`` is recorded whatever the policy: it is a class name, and it
    is what identifies the failure. The MESSAGE is the opposite -- it can quote
    the command line that failed, token included -- so it goes through
    ``policy`` exactly like every other text-bearing field. It is cut to
    :data:`MAX_ERROR_MESSAGE_CHARS` first, so a huge traceback-derived message
    cannot ride along under ``payloads="full"``, and the digest then identifies
    precisely the text that policy would have written.
    """
    return {
        "error_type": type(exc).__name__,
        **payload_attrs("error", str(exc)[:MAX_ERROR_MESSAGE_CHARS], policy),
    }


def screen_digest(snapshot: Snapshot) -> dict[str, Any]:
    """The snapshot scalars worth keeping on every event that observed a screen.

    Free by construction: the caller already holds this snapshot, so reading six
    scalar fields costs nothing -- no extra hash, no extra pass over the cell
    grid. Lengths stand in for the text itself (which is user data).
    """
    return {
        "rows": snapshot.size[0],
        "cols": snapshot.size[1],
        "lines": len(snapshot.lines),
        "selected_line": snapshot.selected_line,
        "alt_screen": snapshot.alt_screen,
        "status_bar_chars": len(snapshot.status_bar or ""),
        "title_chars": len(snapshot.title or ""),
        "errors": len(snapshot.errors),
    }


def _screen_text(snapshot: Snapshot) -> str:
    return snapshot.to_text()


# -- outcome describers -----------------------------------------------------
# One per recorded verb whose return value says something. Module-level (not
# methods) so the disabled path allocates nothing to pass them, and they return
# the private ``_snapshot`` key that :meth:`LoggedSession._timed` expands into
# ``screen_text`` only when ``record_snapshots`` is on.


def _describe_ready(result: Any) -> dict[str, Any]:
    # wait_ready -> (reason, snapshot); reason is MARKER/STABLE/TIMEOUT/EXITED.
    reason, snap = result
    return {"outcome": reason, "screen": screen_digest(snap), "_snapshot": snap}


def _describe_stable(result: Any) -> dict[str, Any]:
    # wait_stable -> True | False | Exited
    if isinstance(result, Exited):   # EXITED is an Exited instance
        return {"outcome": "EXITED"}
    return {"outcome": "STABLE" if result else "TIMEOUT"}


def _describe_match(result: Any) -> dict[str, Any]:
    # wait_for -> (matched, snapshot)
    matched, snap = result
    if isinstance(matched, Exited):
        return {"outcome": "EXITED", "screen": screen_digest(snap), "_snapshot": snap}
    return {"outcome": "MATCHED" if matched else "TIMEOUT",
            "screen": screen_digest(snap), "_snapshot": snap}


def _describe_any(result: Any) -> dict[str, Any]:
    # wait_any -> (index, snapshot); index -1 is the timeout sentinel.
    index, snap = result
    if isinstance(index, Exited):
        return {"outcome": "EXITED", "screen": screen_digest(snap), "_snapshot": snap}
    return {"outcome": "TIMEOUT" if index < 0 else f"PATTERN_{index}",
            "pattern_index": index, "screen": screen_digest(snap), "_snapshot": snap}


def _describe_change(result: Any) -> dict[str, Any]:
    # wait_change / wait_visual_change -> (changed, snapshot)
    changed, snap = result
    if isinstance(changed, Exited):
        return {"outcome": "EXITED", "screen": screen_digest(snap), "_snapshot": snap}
    return {"outcome": "CHANGED" if changed else "TIMEOUT",
            "screen": screen_digest(snap), "_snapshot": snap}


def _describe_snapshot(result: Any) -> dict[str, Any]:
    return {"outcome": "OK", "screen": screen_digest(result), "_snapshot": result}


def _describe_close(result: Any) -> dict[str, Any]:
    # close() -> the close-protocol state dict: what could actually be CONFIRMED.
    return {
        "outcome": "OK",
        "close_requested": bool(result.get("close_requested")),
        "closed_confirmed": bool(result.get("closed_confirmed")),
        "close_unconfirmed": bool(result.get("close_unconfirmed")),
        "output_eof": bool(result.get("output_eof")),
        "generation": result.get("generation"),
        **({"last_progress": str(result.get("last_progress"))[:200]}
           if result.get("last_progress") else {}),
    }


#: verb kind -> describer. Resolved by name so a recorded call passes a string
#: literal (zero allocation) rather than a bound method.
_DESCRIBERS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "ready": _describe_ready,
    "stable": _describe_stable,
    "match": _describe_match,
    "any": _describe_any,
    "change": _describe_change,
    "snapshot": _describe_snapshot,
    "close": _describe_close,
}


@dataclass(frozen=True)
class SessionEvent:
    """One recorded action: envelope + payload, immutable once created."""

    seq: int
    ts: str
    session_id: str
    name: str
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """The envelope as a plain dict, ready for ``json.dumps``."""
        return {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "seq": self.seq,
            "ts": self.ts,
            "session_id": self.session_id,
            "name": self.name,
            "attrs": dict(self.attrs),
        }

    def to_line(self) -> str:
        """The event as one newline-terminated JSON Lines record.

        ``ensure_ascii=False`` keeps non-ASCII screen text readable instead of
        \\u-escaped; ``default=str`` means an attribute nobody anticipated is
        written as its repr rather than raising -- a log that can break the
        session it is describing is worse than no log.
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str) + "\n"


class JsonlFileSink:
    """Append-only JSON Lines file sink: one event per line, flushed per event.

    Flushed on every write on purpose. The case this module exists for is a
    session that died badly; buffered events in a process that then got killed
    are exactly the events that were worth keeping.
    """

    def __init__(self, path: str | os.PathLike[str], *, append: bool = True) -> None:
        self.path = os.fspath(path)
        self._fh = open(self.path, "a" if append else "w", encoding="utf-8", newline="\n")

    def __call__(self, line: str) -> None:
        self._fh.write(line)
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> JsonlFileSink:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_events(path: str | os.PathLike[str], *, strict: bool = False) -> list[dict[str, Any]]:
    """Read a JSON Lines event log back into dicts.

    A malformed line is skipped unless ``strict``. The last line of a crashed
    session's log is routinely half-written, and one truncated tail must not cost
    the reader every event before it -- which is the whole reason JSON Lines was
    chosen over a single JSON array.
    """
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError as exc:
                if strict:
                    raise ValueError(f"{path}: malformed event line: {exc}") from exc
                continue
            if isinstance(obj, dict):
                out.append(obj)
            elif strict:
                raise ValueError(f"{path}: event line is {type(obj).__name__}, not an object")
    return out


class SessionLog:
    """The recorder: sequence numbers, timestamps, payload policy, one sink.

    Constructing one is the entire opt-in. With ``enabled=False`` (or after
    :meth:`close`) :meth:`record` is a branch that returns ``None``, no event is
    built, and the sink is not touched.
    """

    def __init__(
        self,
        session_id: str | None = None,
        sink: Sink | None = None,
        *,
        payloads: str = PAYLOAD_HASH,
        record_snapshots: bool = False,
        queries: str = PAYLOAD_FULL,
        record_pumps: bool = False,
        max_attr_chars: int = DEFAULT_MAX_ATTR_CHARS,
        max_events: int = DEFAULT_MAX_EVENTS,
        wall_clock: Clock | None = None,
        monotonic: Clock | None = None,
        enabled: bool = True,
    ) -> None:
        """Build a recorder.

        Args:
            session_id: identifies the run in a shared log; defaults to a random
                one, because "whose run was this" is unanswerable after the fact.
            sink: called with each finished JSON line (``None`` keeps events in
                memory only).
            payloads: text policy -- ``"hash"`` (default), ``"full"`` or ``"none"``.
            queries: policy for agent-authored queries (the marker/regex/keys an
                agent waited for) -- ``"full"`` (default), ``"hash"`` or
                ``"none"``. Kept separate from ``payloads`` because the two have
                opposite risk profiles: a query is the QUESTION ("wait for >>>"),
                and a log that cannot say what was waited for explains nothing;
                a payload is the program's or the user's DATA, which is where
                credentials live. ``payloads="none", queries="none"`` is the
                scrub-everything mode.
            record_snapshots: also write the screen TEXT on every event that has
                a snapshot. Off by default: a 200x60 screen is the largest
                thing that can go in a log.
            record_pumps: record ``pump()`` calls. Off by default: it is the only
                high-frequency verb here.
            max_attr_chars: per-attribute cut; longer values are truncated and
                marked with how many characters were dropped.
            max_events: size of the in-memory ring (the sink still sees all).
            wall_clock: ``time.time``-shaped seconds -> RFC 3339.
            monotonic: ``time.monotonic``-shaped seconds -> durations.
            enabled: false makes :meth:`record` a no-op branch.
        """
        for name, policy in (("payloads", payloads), ("queries", queries)):
            if policy not in (PAYLOAD_NONE, PAYLOAD_HASH, PAYLOAD_FULL):
                raise ValueError(
                    f"{name} must be one of {PAYLOAD_NONE!r}, {PAYLOAD_HASH!r}, "
                    f"{PAYLOAD_FULL!r}; got {policy!r}")
        self.session_id = session_id or f"s{uuid.uuid4().hex[:12]}"
        self.payloads = payloads
        self.queries = queries
        self.record_snapshots = record_snapshots
        self.record_pumps = record_pumps
        self.max_attr_chars = max(0, int(max_attr_chars))
        self.sink = sink
        self.wall_clock: Clock = wall_clock or time.time
        self.monotonic: Clock = monotonic or time.monotonic
        self._events: deque[SessionEvent] = deque(maxlen=max(1, int(max_events)))
        self._max_events = max(1, int(max_events))
        self._seq = 0
        self._sink_errors = 0
        self._chars = 0
        self._enabled = bool(enabled)

    # -- state -------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Is this log recording? The one check every recorded action makes."""
        return self._enabled

    @property
    def events(self) -> tuple[SessionEvent, ...]:
        """The retained events, oldest first (bounded -- see ``max_events``)."""
        return tuple(self._events)

    def close(self) -> dict[str, Any]:
        """Stop recording and report the accounting. Idempotent.

        Closing the LOG is not closing the session: an event log must never be
        the reason a child process is left running.
        """
        self._enabled = False
        return self.stats()

    def stats(self) -> dict[str, Any]:
        """What this log has cost and kept, for the end-of-run receipt."""
        return {
            "session_id": self.session_id,
            "enabled": self._enabled,
            "recorded": self._seq,
            "retained": len(self._events),
            "max_events": self._max_events,
            "sink_errors": self._sink_errors,
            "chars_written": self._chars,
            "payloads": self.payloads,
            "queries": self.queries,
            "record_snapshots": self.record_snapshots,
            "record_pumps": self.record_pumps,
            "sink": type(self.sink).__name__ if self.sink is not None else None,
        }

    def to_ndjson(self) -> str:
        """The retained events as a JSON Lines document."""
        return "".join(ev.to_line() for ev in self._events)

    # -- recording ---------------------------------------------------------

    def text_attrs(self, key: str, text: str) -> dict[str, Any]:
        """How one piece of PROGRAM-DERIVED text appears, under ``payloads``.

        Always ``<key>_chars``; with ``"hash"`` (the default) also
        ``<key>_sha256_16``; with ``"full"`` also ``<key>``; with ``"none"``
        nothing else. The length is metadata, not content, so it survives even
        the scrub-everything policy.
        """
        return payload_attrs(key, text, self.payloads)

    def query_attrs(self, key: str, text: str) -> dict[str, Any]:
        """Same, for an AGENT-AUTHORED query: a marker, a regex, a key sequence."""
        return payload_attrs(key, text, self.queries)

    def record(self, name: str, attrs: Mapping[str, Any] | None = None,
               **fields: Any) -> SessionEvent | None:
        """Record one event; return it, or ``None`` when this log is disabled.

        A sink that raises is counted in ``stats()["sink_errors"]`` and the event
        is still kept in memory. Rationale: this log is attached to a runtime
        whose job is driving a program, and a full disk or a closed file must
        degrade the record, never the drive.
        """
        if not self._enabled:
            return None
        self._seq += 1
        payload: dict[str, Any] = dict(attrs or ())
        payload.update(fields)
        event = SessionEvent(
            seq=self._seq,
            ts=rfc3339(self.wall_clock()),
            session_id=self.session_id,
            name=name,
            attrs=self._prepare(payload),
        )
        line = event.to_line()
        self._chars += len(line)
        if self.sink is not None:
            try:
                self.sink(line)
            except Exception:  # a broken sink must degrade the record, not the drive
                self._sink_errors += 1
        self._events.append(event)
        return event

    def _prepare(self, attrs: Mapping[str, Any]) -> dict[str, Any]:
        """Cut over-long string values, marking exactly how much was dropped."""
        limit = self.max_attr_chars
        out: dict[str, Any] = {}
        for key, value in attrs.items():
            if limit and isinstance(value, str) and len(value) > limit:
                out[key] = value[:limit] + f"[+{len(value) - limit} chars]"
            else:
                out[key] = value
        return out


class LoggedSession:
    """A :class:`PtySession` that records each action and what came back.

    A transparent wrapper, NOT a subclass: the runtime keeps one class, and the
    log cannot change what a wait does -- it observes the call, its arguments and
    its return value. Methods defined here forward verbatim (their defaults match
    the session's, which ``tests/test_session_log.py`` pins by introspection);
    anything else reaches the real session through ``__getattr__``.

    Event names are the daemon/CLI verb names, namespaced by category:
    ``session.start``, ``session.resize``, ``session.snapshot``,
    ``session.close``, ``session.alive``, ``input.send_text``,
    ``input.send_keys``, ``input.send_line``, ``wait.*``, and ``io.pump``
    (only with ``record_pumps=True``).
    """

    def __init__(self, session: PtySession, log: SessionLog) -> None:
        self._session = session
        self.log = log

    # -- transparent surface -------------------------------------------------

    @property
    def session(self) -> PtySession:
        """The wrapped session, for the calls this class does not record."""
        return self._session

    def __getattr__(self, name: str) -> Any:
        # Reached only for attributes LoggedSession does not define. The guard
        # keeps a lookup before __init__ finished (or during unpickling) from
        # recursing forever through the missing _session.
        if name.startswith("_session"):
            raise AttributeError(name)
        return getattr(self._session, name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Wrapper-local state stays here; everything else is a session attribute
        # and must land on the session. A wrapper that swallowed the write would
        # diverge silently -- setting ``detect_child_exit`` on the wrapper and
        # then reading the session's own ``False`` back is exactly the surprise a
        # transparent wrapper must not have.
        if name in ("_session", "log"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._session, name, value)

    def __enter__(self) -> LoggedSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- recording core -----------------------------------------------------

    def _timed(self, name: str, attrs: Mapping[str, Any] | Callable[[], Mapping[str, Any]],
               call: Callable[[], Any], kind: str | None = None) -> Any:
        """Run ``call``; when the log is on, record ``name`` with the outcome.

        The disabled path -- the default, and the one every existing caller
        takes -- is an attribute load, one branch, and the call: ``attrs`` is
        only built by the callback when logging is actually on, so opting out
        allocates nothing.

        An exception from ``call`` is recorded and then RE-RAISED: the log
        observes, it never absorbs.
        """
        log = self.log
        if not log.enabled:
            return call()
        payload = dict(attrs() if callable(attrs) else attrs)
        t0 = log.monotonic()
        try:
            result = call()
        except Exception as exc:
            payload.update(error_attrs(exc, policy=log.payloads))
            log.record(name, payload, elapsed_ms=round((log.monotonic() - t0) * 1000.0, 3))
            raise
        if kind is not None:
            described = _DESCRIBERS[kind](result)
            snapshot = described.pop("_snapshot", None)
            if snapshot is not None and log.record_snapshots:
                described["screen_text"] = _screen_text(snapshot)
            payload.update(described)
        log.record(name, payload, elapsed_ms=round((log.monotonic() - t0) * 1000.0, 3))
        return result

    # -- lifecycle ----------------------------------------------------------

    def start(self, cmd: str | Sequence[str]) -> None:
        self._timed("session.start", lambda: self._cmd_attrs(cmd),
                    lambda: self._session.start(cmd))

    def _cmd_attrs(self, cmd: str | Sequence[str]) -> dict[str, Any]:
        """argv, described without writing it down by default.

        Only a real ``Sequence`` is enumerated: something one-shot (an iterator
        a caller passed anyway) is reported as an unknown count rather than
        consumed by the log before the session gets to spawn it. And it runs
        only when the log is ON, so the disabled path never builds the string.
        """
        if isinstance(cmd, str):
            return {"argv_count": 1, **self.log.text_attrs("cmd", cmd)}
        if not isinstance(cmd, Sequence):
            return {"argv_count": None}
        parts = [str(part) for part in cmd]
        return {"argv_count": len(parts),
                **self.log.text_attrs("cmd", " ".join(parts))}

    def close(self) -> dict:
        return self._timed("session.close", {}, lambda: self._session.close(), "close")

    def resize(self, cols: int, rows: int) -> None:
        self._timed("session.resize", lambda: {"cols": cols, "rows": rows},
                    lambda: self._session.resize(cols, rows))

    def is_alive(self) -> bool:
        return bool(self._timed("session.alive", {}, lambda: self._session.is_alive()))

    # -- input --------------------------------------------------------------

    def send_text(self, text: str) -> None:
        self._timed("input.send_text",
                    lambda: {"bytes": len(text.encode("utf-8")),
                             **self.log.text_attrs("text", text)},
                    lambda: self._session.send_text(text))

    def send_line(self, text: str) -> None:
        self._timed("input.send_line",
                    lambda: {"bytes": len(text.encode("utf-8")),
                             **self.log.text_attrs("text", text)},
                    lambda: self._session.send_line(text))

    def send_keys(self, keys: list[str]) -> None:
        self._timed("input.send_keys",
                    lambda: {"key_count": len(keys),
                             **self.log.query_attrs("tokens", " ".join(keys))},
                    lambda: self._session.send_keys(keys))

    # -- perception ---------------------------------------------------------

    def snapshot(self) -> Snapshot:
        return self._timed("session.snapshot", {}, lambda: self._session.snapshot(),
                           "snapshot")

    def pump(self, max_bytes: int | None = None) -> bytes:
        if not self.log.record_pumps:
            return self._session.pump(max_bytes)
        return self._timed("io.pump", lambda: {"max_bytes": max_bytes},
                           lambda: self._session.pump(max_bytes))

    # -- waits --------------------------------------------------------------

    def wait_ready(
        self,
        marker: str | None = None,
        quiet_ms: int = 200,
        poll_ms: int = 30,
        max_wait_ms: int = 10000,
        min_wait_ms: int = 50,
        grace_ms: int = 40,
        flags: int = 0,
        on_poll: PollHook = None,
        alive_fn: AliveFn = None,
        after_revision: int | None = None,
    ) -> tuple[str, Snapshot]:
        return self._timed(
            "wait.wait_ready",
            lambda: {
                **(self.log.query_attrs("marker", marker)
                  if marker is not None else {"marker": None}),
                "quiet_ms": quiet_ms, "max_wait_ms": max_wait_ms,
                "min_wait_ms": min_wait_ms, "grace_ms": grace_ms, "poll_ms": poll_ms,
                "flags": flags, "on_poll": on_poll is not None,
                "alive_watch": alive_fn is not None,
                "after_revision": after_revision,
            },
            lambda: self._session.wait_ready(
                marker=marker, quiet_ms=quiet_ms, poll_ms=poll_ms,
                max_wait_ms=max_wait_ms, min_wait_ms=min_wait_ms, grace_ms=grace_ms,
                flags=flags, on_poll=on_poll, alive_fn=alive_fn,
                after_revision=after_revision),
            "ready",
        )

    def wait_stable(
        self,
        quiet_ms: int = 200,
        poll_ms: int = 30,
        max_wait_ms: int = 8000,
        grace_ms: int = 40,
        min_wait_ms: int = 0,
        on_poll: PollHook = None,
        alive_fn: AliveFn = None,
        after_revision: int | None = None,
    ) -> bool | Exited:
        return self._timed(
            "wait.wait_stable",
            lambda: {
                "quiet_ms": quiet_ms, "max_wait_ms": max_wait_ms, "grace_ms": grace_ms,
                "min_wait_ms": min_wait_ms, "poll_ms": poll_ms,
                "on_poll": on_poll is not None, "alive_watch": alive_fn is not None,
                "after_revision": after_revision,
            },
            lambda: self._session.wait_stable(
                quiet_ms=quiet_ms, poll_ms=poll_ms, max_wait_ms=max_wait_ms,
                grace_ms=grace_ms, min_wait_ms=min_wait_ms,
                on_poll=on_poll, alive_fn=alive_fn,
                after_revision=after_revision),
            "stable",
        )

    def wait_for(
        self,
        pattern: str,
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        min_wait_ms: int = 0,
        flags: int = 0,
        on_poll: PollHook = None,
        alive_fn: AliveFn = None,
        after_revision: int | None = None,
    ) -> tuple[bool | Exited, Snapshot]:
        return self._timed(
            "wait.wait_for",
            lambda: {
                **self.log.query_attrs("pattern", pattern),
                "timeout_ms": timeout_ms, "poll_ms": poll_ms,
                "min_wait_ms": min_wait_ms, "flags": flags,
                "on_poll": on_poll is not None, "alive_watch": alive_fn is not None,
                "after_revision": after_revision,
            },
            lambda: self._session.wait_for(
                pattern, timeout_ms=timeout_ms, poll_ms=poll_ms,
                min_wait_ms=min_wait_ms, flags=flags, on_poll=on_poll,
                alive_fn=alive_fn, after_revision=after_revision),
            "match",
        )

    def wait_any(
        self,
        patterns: Sequence[str],
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        min_wait_ms: int = 0,
        flags: int = 0,
        on_poll: PollHook = None,
        alive_fn: AliveFn = None,
        after_revision: int | None = None,
    ) -> tuple[int | Exited, Snapshot]:
        return self._timed(
            "wait.wait_any",
            lambda: {
                **self.log.query_attrs("patterns", "\n".join(patterns)),
                "timeout_ms": timeout_ms,
                "poll_ms": poll_ms, "min_wait_ms": min_wait_ms, "flags": flags,
                "on_poll": on_poll is not None, "alive_watch": alive_fn is not None,
                "after_revision": after_revision,
            },
            lambda: self._session.wait_any(
                patterns, timeout_ms=timeout_ms, poll_ms=poll_ms,
                min_wait_ms=min_wait_ms, flags=flags, on_poll=on_poll,
                alive_fn=alive_fn, after_revision=after_revision),
            "any",
        )

    def wait_change(
        self,
        baseline_hash: int | None = None,
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        on_poll: PollHook = None,
        alive_fn: AliveFn = None,
        after_revision: int | None = None,
    ) -> tuple[bool | Exited, Snapshot]:
        return self._timed(
            "wait.wait_change",
            lambda: {
                "baseline_hash": baseline_hash, "timeout_ms": timeout_ms,
                "poll_ms": poll_ms, "on_poll": on_poll is not None,
                "alive_watch": alive_fn is not None,
                "after_revision": after_revision,
            },
            lambda: self._session.wait_change(
                baseline_hash=baseline_hash, timeout_ms=timeout_ms, poll_ms=poll_ms,
                on_poll=on_poll, alive_fn=alive_fn,
                after_revision=after_revision),
            "change",
        )

    def wait_visual_change(
        self,
        baseline_hash: int | None = None,
        timeout_ms: int = 10000,
        poll_ms: int = 30,
        on_poll: PollHook = None,
        alive_fn: AliveFn = None,
        after_revision: int | None = None,
    ) -> tuple[bool | Exited, Snapshot]:
        return self._timed(
            "wait.wait_visual_change",
            lambda: {
                "baseline_hash": baseline_hash, "timeout_ms": timeout_ms,
                "poll_ms": poll_ms, "on_poll": on_poll is not None,
                "alive_watch": alive_fn is not None,
                "after_revision": after_revision,
            },
            lambda: self._session.wait_visual_change(
                baseline_hash=baseline_hash, timeout_ms=timeout_ms, poll_ms=poll_ms,
                on_poll=on_poll, alive_fn=alive_fn,
                after_revision=after_revision),
            "change",
        )
