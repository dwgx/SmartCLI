#!/usr/bin/env python3
"""test_session_log.py — a driving session that failed leaves no evidence.

`PtySession` keeps only *current* state: a screen model, an io ledger, a close
protocol. When a run goes wrong — the wait that timed out, the keystroke that
went somewhere else, the child that died on the third prompt — nothing in it
answers "what did I ask for, what came back, and how long did it take". This
gate is for `smartcli_core/sessionlog.py`, the opt-in JSON Lines record of that.

Covered here:
  * OFF BY DEFAULT: a disabled log records nothing, touches no sink, and a
    `LoggedSession` over it drives a real `PtySession` to byte-identical results.
    Nothing is wired into `PtySession` itself — asserted, not assumed.
  * SHAPE: one event per action, each line a JSON object with the exact envelope
    (schema, version, seq, ts, session_id, name, attrs), seq dense from 1,
    timestamps RFC 3339 UTC with microseconds, one round-trip through a real
    file and back through `read_events`.
  * NOT WRITTEN DOWN: typed text and argv are digests by default, never clear
    text; the digest still answers "were these the same two inputs?".
  * QUERIES vs PAYLOADS: an agent's marker/regex is the question and is kept
    verbatim by default; payloads are the program's/user's data and are not.
  * EVERY OUTCOME: MARKER / STABLE / TIMEOUT / EXITED / MATCHED / PATTERN_n /
    CHANGED, each recorded exactly as the wait reported it, with the free screen
    digest; screen TEXT only when asked.
  * FAILURE IS STILL RECORDED: a raising call is logged with its error type and
    re-raised; a raising sink degrades the record and never the drive.
  * BOUNDS: the in-memory ring is bounded, long attributes are cut with a count,
    `close()` stops recording without touching the child, and a truncated final
    line does not cost the reader the events before it.
  * NO DRIFT: `LoggedSession`'s recorded methods have the same parameter names and
    defaults as `PtySession`'s, checked by introspection — so a wrapper can never
    quietly default a wait differently from the runtime it wraps.

Pure/in-memory: a fake backend (no PTY, no child process), a JSON Lines file in
a temp dir, and injected clocks — nothing here sleeps for real or spawns
anything.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
import tempfile
import time as _real_time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core import PtySession  # noqa: E402
from smartcli_core.pty_backend import PtyBackend  # noqa: E402
from smartcli_core.readiness import EXITED_REASON  # noqa: E402
from smartcli_core.sessionlog import (  # noqa: E402
    PAYLOAD_FULL,
    PAYLOAD_HASH,
    PAYLOAD_NONE,
    SCHEMA,
    SCHEMA_VERSION,
    JsonlFileSink,
    LoggedSession,
    SessionLog,
    read_events,
    text_fingerprint,
)

_fails: list[str] = []


def check(cond, name, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        _fails.append(name)


# -- fakes -----------------------------------------------------------------


class SteppingClock:
    """A clock that advances a fixed step on every read.

    Injecting it makes every timestamp and every ``elapsed_ms`` in the log an
    exact value instead of something to assert with a tolerance.
    """

    def __init__(self, step: float, start: float = 1_700_000_000.0) -> None:
        self.t = start
        self.step = step
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        self.t += self.step
        return self.t


class ScriptedBackend(PtyBackend):
    """Fake backend: queued byte batches in, written bytes recorded, no process."""

    def __init__(self) -> None:
        self.queue: list[bytes] = []
        self.written = bytearray()
        self.spawned = None
        self.size = (0, 0)
        self._alive = True
        self.write_error: Exception | None = None
        self.read_error: Exception | None = None

    def feed(self, data: bytes) -> None:
        self.queue.append(data)

    def spawn(self, cmd, cols, rows):
        self.spawned = cmd
        self.size = (cols, rows)

    def read_nonblocking(self, timeout=0.0):
        if self.read_error is not None:
            raise self.read_error
        return self.queue.pop(0) if self.queue else b""

    def write(self, data):
        if self.write_error is not None:
            raise self.write_error
        self.written.extend(data)

    def resize(self, cols, rows):
        self.size = (cols, rows)

    def is_alive(self):
        return self._alive

    def terminate(self):
        self._alive = False

def build(sink=None, **log_kw):
    """A logged session over a fake backend, with injected clocks."""
    backend = ScriptedBackend()
    session = PtySession(cols=40, rows=10, backend=backend)
    collected: list[str] = []
    log = SessionLog("agent-test", sink if sink is not None else collected.append,
                     wall_clock=SteppingClock(0.5), monotonic=SteppingClock(0.25),
                     **log_kw)
    return backend, session, log, LoggedSession(session, log)


def names_of(log) -> list[str]:
    return [ev.name for ev in log.events]


def attrs_named(log, name, index=-1) -> dict:
    return log.events[index].attrs


# =========================================================================
# Off by default
# =========================================================================


def test_disabled_log_is_a_branch():
    seen: list[str] = []
    log = SessionLog("off", seen.append, enabled=False, wall_clock=SteppingClock(0.5),
                     monotonic=SteppingClock(0.25))
    result = log.record("session.start", {"cmd_chars": 3})
    check(result is None, "disabled log: record() returns None, not an event")
    check(seen == [], "disabled log: the sink is never called", f"sink saw {seen!r}")
    stats = log.stats()
    check(stats["recorded"] == 0 and stats["enabled"] is False,
          "disabled log: stats report zero recorded", f"stats={stats}")
    check(log.events == (), "disabled log: nothing retained in memory")


def test_disabled_wrapper_drives_identically():
    """The opt-out must be a no-op on the DRIVE, not just on the recorder."""
    backend, _session, log, logged = build(enabled=False)
    backend.feed(b">>> ")
    logged.start("python")
    logged.send_line("print(6*7)")
    reason, snap = logged.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
    check(reason == "MARKER", "disabled log: the wait still returns MARKER", f"reason={reason}")
    check(">>>" in snap.to_text(), "disabled log: the snapshot is the real screen")
    check(bytes(backend.written).endswith(b"\r"),
          "disabled log: input still reached the pty", f"written={bytes(backend.written)!r}")
    check(log.stats()["recorded"] == 0, "disabled log: driving recorded nothing")

    # And the same drive on a bare session gives the same answers.
    bare = ScriptedBackend()
    plain = PtySession(cols=40, rows=10, backend=bare)
    bare.feed(b">>> ")
    plain.start("python")
    plain.send_line("print(6*7)")
    plain_reason, plain_snap = plain.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
    check((reason, snap.to_text()) == (plain_reason, plain_snap.to_text()),
          "disabled log: wrapped and bare sessions agree exactly")


def test_nothing_is_wired_into_the_session():
    check(not hasattr(PtySession, "log") and not hasattr(PtySession, "_session_log"),
          "off by default: PtySession carries no log attribute or hook")
    sig = inspect.signature(PtySession.__init__)
    check("log" not in sig.parameters and "sessionlog" not in sig.parameters,
          "off by default: PtySession.__init__ takes no logging argument",
          f"params={list(sig.parameters)}")


# =========================================================================
# Shape
# =========================================================================


def test_one_line_per_action_with_a_fixed_envelope():
    backend, _session, log, logged = build()
    backend.feed(b">>> ")
    logged.start(["python", "-i"])
    logged.send_line("print(6*7)")
    logged.send_keys(["Down", "Enter"])
    logged.resize(80, 24)
    reason, _snap = logged.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
    logged.is_alive()
    logged.snapshot()
    logged.close()

    check(names_of(log) == [
        "session.start", "input.send_line", "input.send_keys", "session.resize",
        "wait.wait_ready", "session.alive", "session.snapshot", "session.close",
    ], "one event per action, in order, named after the CLI verbs",
        f"names={names_of(log)}")

    lines = log.to_ndjson().splitlines()
    check(len(lines) == len(log.events) == 8,
          "one JSON Lines record per event", f"lines={len(lines)} events={len(log.events)}")
    envelope = {"schema", "schema_version", "seq", "ts", "session_id", "name", "attrs"}
    parsed = [json.loads(raw) for raw in lines]
    odd = [sorted(ev) for ev in parsed if set(ev) != envelope]
    check(not odd, "every event carries exactly the envelope keys", f"offenders={odd}")
    check(all(ev["schema"] == SCHEMA and ev["schema_version"] == SCHEMA_VERSION
              for ev in parsed), "every event names the schema and its version")
    seqs = [ev["seq"] for ev in parsed]
    check(seqs == list(range(1, len(lines) + 1)), "seq is dense and monotone from 1",
          f"seqs={seqs}")
    stamps = [ev["ts"] for ev in parsed]
    ts_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
    check(all(ts_re.match(t) for t in stamps),
          "timestamps are RFC 3339 UTC with microseconds", f"ts[0]={stamps[0]}")
    check(stamps == sorted(stamps), "timestamps sort chronologically as strings")
    check(all(ev["session_id"] == "agent-test" for ev in parsed),
          "every event carries the session id")


def test_file_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "run.jsonl")
        backend, _session, log, logged = build()
        with JsonlFileSink(path) as sink:
            log.sink = sink
            backend.feed(b">>> ")
            logged.start("python")
            logged.send_line("print(1)")
            logged.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
        raw = Path(path).read_text(encoding="utf-8")
        check(raw.endswith("\n"), "the file ends on a record boundary")
        check(len(raw.splitlines()) == 3, "three actions -> three lines",
              f"lines={len(raw.splitlines())}")
        back = read_events(path)
        check(back == [ev.to_dict() for ev in log.events],
              "what was written reads back identical to what was recorded")
        check(log.stats()["sink"] == "JsonlFileSink", "stats name the sink in use")


# =========================================================================
# What is (and is not) written down
# =========================================================================


def test_payload_text_is_hashed_not_written():
    backend, _session, log, logged = build()
    logged.send_text("hunter2")
    logged.send_text("hunter2")
    logged.send_text("correct horse")
    first = attrs_named(log, "input.send_text", 0)
    check("text" not in first, "typed text is NOT written in clear by default",
          f"attrs={first}")
    check(first["text_chars"] == 7 and first["bytes"] == 7,
          "the length and byte count are kept", f"attrs={first}")
    check(first["text_sha256_16"] == text_fingerprint("hunter2"),
          "the digest is the documented sha256 prefix")
    check(attrs_named(log, "input.send_text", 1)["text_sha256_16"]
          == first["text_sha256_16"],
          "the same input twice carries the same digest — a retry is detectable")
    check(attrs_named(log, "input.send_text", 2)["text_sha256_16"]
          != first["text_sha256_16"],
          "a DIFFERENT input carries a different digest")
    check(json.dumps(log.to_ndjson()).find("hunter2") == -1,
          "the secret appears nowhere in the serialised log")

    _b, _s, full, logged_full = build(payloads=PAYLOAD_FULL)
    logged_full.send_text("hunter2")
    check(attrs_named(full, "input.send_text").get("text") == "hunter2",
          "payloads='full' opts into clear text on purpose")

    _b, _s, bare, logged_bare = build(payloads=PAYLOAD_NONE)
    logged_bare.send_text("hunter2")
    scrubbed = attrs_named(bare, "input.send_text")
    check("text" not in scrubbed and "text_sha256_16" not in scrubbed
          and scrubbed["text_chars"] == 7,
          "payloads='none' keeps only the length", f"attrs={scrubbed}")


def test_argv_is_not_written_in_clear_by_default():
    _b, _s, log, logged = build()
    logged.start(["ssh", "agent@host", "--token", "s3cret"])
    attrs = attrs_named(log, "session.start")
    check("cmd" not in attrs and attrs["argv_count"] == 4,
          "argv is not recorded in clear by default", f"attrs={attrs}")
    check("s3cret" not in log.to_ndjson(), "the token is nowhere in the log")
    _b, _s, full, logged_full = build(payloads=PAYLOAD_FULL)
    logged_full.start("python -i")
    check(attrs_named(full, "session.start").get("cmd") == "python -i",
          "payloads='full' records the command line")


def test_queries_are_kept_verbatim_and_can_be_scrubbed():
    backend, _session, log, logged = build()
    backend.feed(b">>> ")
    logged.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
    attrs = attrs_named(log, "wait.wait_ready")
    check(attrs["marker"] == ">>> ",
          "the marker the agent waited for is recorded verbatim (queries='full')",
          f"attrs={attrs}")
    check(attrs["alive_watch"] is False,
          "whether a liveness predicate was in play is recorded")

    _b, _s, scrubbed, logged_scrubbed = build(queries=PAYLOAD_NONE)
    logged_scrubbed.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
    q = attrs_named(scrubbed, "wait.wait_ready")
    check("marker" not in q and q["marker_chars"] == 4,
          "queries='none' leaves only the length", f"attrs={q}")

    _b, _s, hashed, logged_hashed = build(queries=PAYLOAD_HASH)
    logged_hashed.wait_for("prompt", timeout_ms=0)
    p = attrs_named(hashed, "wait.wait_for")
    check("pattern" not in p and p["pattern_sha256_16"] == text_fingerprint("prompt"),
          "queries='hash' keeps the digest", f"attrs={p}")


def test_key_tokens_are_recorded_as_a_query():
    _b, _s, log, logged = build()
    logged.send_keys(["Down", "Down", "Enter"])
    attrs = attrs_named(log, "input.send_keys")
    check(attrs["key_count"] == 3 and attrs["tokens"] == "Down Down Enter",
          "key names are recorded so the log says what was pressed", f"attrs={attrs}")


# =========================================================================
# Outcomes
# =========================================================================


def test_every_wait_outcome_is_recorded_as_reported():
    backend, _session, log, logged = build()
    # wait_ready: content, death, and the ceiling are three different outcomes.
    backend.feed(b">>> ")
    got = logged.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
    logged.wait_ready(marker="never-appears", min_wait_ms=0, max_wait_ms=0,
                      alive_fn=lambda: False)
    logged.wait_ready(marker="never-appears", min_wait_ms=0, max_wait_ms=0)
    # wait_for: the same three.
    logged.wait_for("nope", timeout_ms=0)
    logged.wait_for(">>> ", timeout_ms=0)
    logged.wait_for("never", timeout_ms=0, alive_fn=lambda: False)
    # wait_any: WHICH pattern, none, death.
    backend.feed(b"b")
    logged.wait_any(["nope", "b"], timeout_ms=0)
    logged.wait_any(["nope", "zzz"], timeout_ms=0)
    logged.wait_any(["nope"], timeout_ms=0, alive_fn=lambda: False)
    # the change waits: a byte arrives, then nothing arrives.
    backend.feed(b"z")
    logged.wait_change(timeout_ms=0)
    logged.wait_change(timeout_ms=0)
    backend.feed(b"y")
    logged.wait_visual_change(timeout_ms=0)
    # wait_stable: settled, ceiling, death.
    logged.wait_stable(quiet_ms=0, grace_ms=0, min_wait_ms=0, poll_ms=0, max_wait_ms=50)
    logged.wait_stable(quiet_ms=0, grace_ms=0, min_wait_ms=0, poll_ms=0, max_wait_ms=0)
    logged.wait_stable(quiet_ms=0, grace_ms=0, min_wait_ms=0, poll_ms=0, max_wait_ms=0,
                       alive_fn=lambda: False)

    outcomes = [ev.attrs.get("outcome") for ev in log.events]
    check(outcomes == ["MARKER", EXITED_REASON, "TIMEOUT",
                       "TIMEOUT", "MATCHED", EXITED_REASON,
                       "PATTERN_1", "TIMEOUT", EXITED_REASON,
                       "CHANGED", "TIMEOUT", "CHANGED",
                       "STABLE", "TIMEOUT", EXITED_REASON],
          "every wait outcome is recorded exactly as the wait reported it",
          f"outcomes={outcomes}")
    check(got[0] == "MARKER", "…and the recorded value agrees with the returned one")
    any_attrs = attrs_named(log, "wait.wait_any", 6)
    check(any_attrs["pattern_index"] == 1,
          "wait_any records WHICH pattern won, not just that one did",
          f"attrs={any_attrs}")


def test_screen_digest_is_free_and_text_is_opt_in():
    backend, _session, log, logged = build()
    backend.feed(b">>> ")
    logged.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
    screen = attrs_named(log, "wait.wait_ready").get("screen")
    check(isinstance(screen, dict) and screen["cols"] == 40 and screen["rows"] == 10,
          "a wait's event carries the screen digest by default", f"screen={screen}")
    check("screen_text" not in attrs_named(log, "wait.wait_ready"),
          "the screen TEXT is not recorded unless asked")

    backend2, _s2, full, logged_full = build(record_snapshots=True)
    backend2.feed(b">>> ")
    logged_full.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
    text = attrs_named(full, "wait.wait_ready").get("screen_text", "")
    check(">>>" in text, "record_snapshots=True adds the rendered screen",
          f"screen_text={text!r}")


def test_elapsed_comes_from_the_injected_clock():
    _b, _s, log, logged = build()
    logged.send_line("x")
    logged.is_alive()
    check(all(ev.attrs["elapsed_ms"] == 250.0 for ev in log.events),
          "elapsed_ms is measured on the log's own monotonic clock (0.25s step)",
          f"elapsed={[ev.attrs['elapsed_ms'] for ev in log.events]}")


# =========================================================================
# Failure still gets recorded
# =========================================================================


def test_error_is_recorded_then_reraised():
    backend, _session, log, logged = build()
    backend.write_error = OSError("pty gone")
    raised = None
    try:
        logged.send_line("hello")
    except OSError as exc:
        raised = exc
    check(isinstance(raised, OSError), "a failing call still raises to the caller")
    attrs = attrs_named(log, "input.send_line")
    check(attrs.get("error_type") == "OSError",
          "the failure is in the log with its type", f"attrs={attrs}")
    check("pty gone" in attrs.get("error_message", ""),
          "the message is kept, cut to a length", f"attrs={attrs}")
    check("outcome" not in attrs, "a failed action is not dressed up as an outcome")


def test_broken_sink_degrades_the_record_not_the_drive():
    def angry(_line):
        raise OSError("no space left on device")

    backend, _session, log, logged = build(sink=angry)
    logged.send_line("still works")
    backend.feed(b">>> ")
    reason, _snap = logged.wait_ready(marker=">>> ", min_wait_ms=0, max_wait_ms=0)
    check(reason == "MARKER", "a broken sink does not break the drive", f"reason={reason}")
    check(bytes(backend.written).endswith(b"\r"), "input still reached the pty")
    stats = log.stats()
    check(stats["sink_errors"] == 2 and stats["recorded"] == 2,
          "the sink failures are counted, not swallowed silently", f"stats={stats}")
    check(len(log.events) == 2, "the events are still in memory when the sink is gone")


def test_close_stops_recording_but_not_the_child():
    backend, _session, log, logged = build()
    logged.send_line("one")
    stats = log.close()
    check(stats["enabled"] is False and stats["recorded"] == 1,
          "close() reports the accounting and stops", f"stats={stats}")
    logged.send_line("two")
    check(log.stats()["recorded"] == 1, "nothing is recorded after close()")
    check(backend.is_alive(), "closing the LOG does not terminate the child")
    check(log.close()["recorded"] == 1, "close() is idempotent")


# =========================================================================
# Bounds
# =========================================================================


def test_in_memory_ring_is_bounded():
    lines: list[str] = []
    log = SessionLog("ring", lines.append, max_events=3, wall_clock=SteppingClock(0.5),
                     monotonic=SteppingClock(0.25))
    for i in range(5):
        log.record("input.send_text", {"n": i})
    stats = log.stats()
    check(stats["recorded"] == 5 and stats["retained"] == 3,
          "the in-memory ring is bounded; the sink saw everything",
          f"stats={stats}")
    check([ev.seq for ev in log.events] == [3, 4, 5],
          "the ring keeps the newest events", f"seqs={[ev.seq for ev in log.events]}")
    check(len(lines) == 5, "no event is lost from the file sink")


def test_long_attributes_are_cut_with_a_count():
    _b, _s, log, logged = build(max_attr_chars=8)
    logged.wait_for("x" * 40, timeout_ms=0)
    value = attrs_named(log, "wait.wait_for")["pattern"]
    check(value == "xxxxxxxx[+32 chars]",
          "an over-long attribute is cut and says how much was dropped", f"value={value!r}")
    check(attrs_named(log, "wait.wait_for")["pattern_chars"] == 40,
          "the untruncated length is still reported")


def test_truncated_tail_does_not_cost_the_reader_the_log():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "crashed.jsonl")
        log = SessionLog("tail", None, wall_clock=SteppingClock(0.5),
                         monotonic=SteppingClock(0.25))
        for i in range(3):
            log.record("input.send_text", {"n": i})
        Path(path).write_text(log.to_ndjson() + '{"schema":"smartcli.sess',
                               encoding="utf-8")
        back = read_events(path)
        check(len(back) == 3, "a half-written final line is skipped, the rest survives",
              f"events={len(back)}")
        strict_failed = False
        try:
            read_events(path, strict=True)
        except ValueError:
            strict_failed = True
        check(strict_failed, "strict=True refuses a malformed line instead")


def test_pump_events_are_opt_in():
    backend, _session, log, logged = build()
    backend.feed(b"x")
    logged.pump()
    check(names_of(log) == [], "pump() is not recorded by default", f"names={names_of(log)}")
    check(logged.pump() == b"", "…and it still pumps")

    backend2, _s2, log2, logged2 = build(record_pumps=True)
    backend2.feed(b"y")
    data = logged2.pump(max_bytes=None)
    check(names_of(log2) == ["io.pump"], "record_pumps=True records the read",
          f"names={names_of(log2)}")
    check(data == b"y" and attrs_named(log2, "io.pump")["max_bytes"] is None,
          "the bytes still come back and the budget is recorded")


# =========================================================================
# Transparency and drift
# =========================================================================


def test_unrecorded_surface_passes_through():
    backend, session, log, logged = build()
    check(logged.session is session, "the wrapped session is reachable")
    check(logged.model is session.model and logged.cols == 40 and logged.rows == 10,
          "attributes the wrapper does not define reach the real session")
    io = logged.io_state()
    check(isinstance(io, dict) and "io" in io, "an unrecorded method forwards verbatim")
    logged.detect_child_exit = True
    check(session.detect_child_exit is True, "setting an attribute on the wrapper sets it "
          "on the session")
    check(hasattr(logged, "definitely_not_a_session_attr") is False,
          "a missing attribute still raises AttributeError through the wrapper")
    guard_failed = False
    try:
        logged._session_missing  # noqa: B018 - the guard is the point
    except AttributeError:
        guard_failed = True
    check(guard_failed, "the __getattr__ guard cannot recurse on a missing _session")
    check(log.stats()["recorded"] == 0,
          "touching unrecorded attributes records nothing", f"names={names_of(log)}")


class OneShot:
    """Iterable exactly once: a second pass yields nothing, like a generator."""

    def __init__(self, items) -> None:
        self.items = list(items)
        self.spent = False

    def __iter__(self):
        if self.spent:
            return iter(())
        self.spent = True
        return iter(self.items)


def test_the_log_never_consumes_what_it_describes():
    """A log that enumerates a one-shot command breaks a call that worked."""
    backend, _session, log, logged = build()
    cmd = OneShot(["python", "-i"])
    logged.start(cmd)
    check(cmd.spent is False,
          "an argv the log cannot safely enumerate is not enumerated")
    check(backend.spawned is cmd and cmd.items == ["python", "-i"],
          "the session received the command object intact")
    check(attrs_named(log, "session.start").get("argv_count") is None,
          "an unenumerable argv is reported as unknown, not guessed")
    check(attrs_named(log, "session.start").get("cmd_chars") is None,
          "and nothing about it is written down")

    backend2, _s2, log2, logged2 = build(enabled=False)
    cmd2 = OneShot(["bash"])
    logged2.start(cmd2)
    check(cmd2.spent is False and backend2.spawned is cmd2,
          "the disabled path does not touch the command either")


def test_wrapper_signatures_match_the_session():
    """A wrapper that defaults a wait differently is a silent behaviour change."""
    methods = ("start", "close", "resize", "is_alive", "send_text", "send_keys",
               "send_line", "snapshot", "pump", "wait_ready", "wait_stable",
               "wait_for", "wait_any", "wait_change", "wait_visual_change")
    for name in methods:
        wrapped = inspect.signature(getattr(LoggedSession, name)).parameters
        plain = inspect.signature(getattr(PtySession, name)).parameters
        check(list(wrapped) == list(plain),
              f"{name}: same parameter names as PtySession",
              f"{list(wrapped)} vs {list(plain)}")
        mismatched = [p for p in plain
                      if wrapped[p].default != plain[p].default or p in ("args", "kwargs")]
        check(not mismatched, f"{name}: every default matches PtySession",
              f"differs at {mismatched}")


def main() -> int:
    t0 = _real_time.perf_counter()
    print("=" * 68)
    print("opt-in session event log (in-memory + temp file; no PTY, no child process)")
    print("=" * 68)
    for fn in (
        test_disabled_log_is_a_branch,
        test_disabled_wrapper_drives_identically,
        test_nothing_is_wired_into_the_session,
        test_one_line_per_action_with_a_fixed_envelope,
        test_file_round_trip,
        test_payload_text_is_hashed_not_written,
        test_argv_is_not_written_in_clear_by_default,
        test_queries_are_kept_verbatim_and_can_be_scrubbed,
        test_key_tokens_are_recorded_as_a_query,
        test_every_wait_outcome_is_recorded_as_reported,
        test_screen_digest_is_free_and_text_is_opt_in,
        test_elapsed_comes_from_the_injected_clock,
        test_error_is_recorded_then_reraised,
        test_broken_sink_degrades_the_record_not_the_drive,
        test_close_stops_recording_but_not_the_child,
        test_in_memory_ring_is_bounded,
        test_long_attributes_are_cut_with_a_count,
        test_truncated_tail_does_not_cost_the_reader_the_log,
        test_pump_events_are_opt_in,
        test_unrecorded_surface_passes_through,
        test_the_log_never_consumes_what_it_describes,
        test_wrapper_signatures_match_the_session,
    ):
        fn()
    wall = _real_time.perf_counter() - t0
    print("-" * 68)
    if _fails:
        print(f"FAIL: {len(_fails)} check(s) failed: {_fails}")
        return 1
    print(f"PASS: a failed session leaves a readable trail, in {wall * 1000:.0f} ms wall")
    return 0


if __name__ == "__main__":
    sys.exit(main())

