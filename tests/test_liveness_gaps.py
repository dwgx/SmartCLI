"""S6 / A05 / A06 — the three liveness gaps the 0.3.0 review named.

Each one is a way for the daemon to stop serving while nothing looks broken:

  * **S6** — a device reply the transport will not take is reported but never
    resumed, so the child that is BLOCKED waiting for its answer stays blocked;
  * **A05** — the ``64`` next to the reader/jobs path was a filter over a list,
    not an admission limit, so a client could make the daemon carry more work
    than the cap suggested;
  * **A06** — ``_reply`` used ``sendall`` on a blocking socket under a 60 s
    timeout, so one peer that stopped reading held the session's only worker —
    and therefore every other caller of that session — for up to a minute.

No PTY and no child process anywhere below. The S6 cases drive the real
``PtySession`` with an injected transport; the A05/A06 cases drive the REAL
``_serve_forever`` over a real loopback socket with a fake session, the same rig
``tests/test_daemon_concurrency.py`` uses.
``SMARTCLI_REPLY_STALL_SECONDS`` is pinned small BEFORE the daemon module is
imported: that window is a module constant, and both "a peer that stops reading is
released inside it" and "a slow-but-reading peer is not" are only measurable against
a small one. The reply CEILING (``POST_AUTH_TIMEOUT``) is deliberately left at its
default 60 s in this file, so the same run also shows the healthy path's patience is
exactly what it was before A06.

Run: python -B tests/test_liveness_gaps.py [--repo PATH]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
REPO = args.repo.resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
TUI_DIR = REPO / "skills" / "drive-tui" / "scripts"
sys.path.insert(0, str(TUI_DIR))

# The daemon reads these at import; pin the stall window before the import below.
os.environ["SMARTCLI_REPLY_STALL_SECONDS"] = "0.4"

try:
    import smartcli_core
    from smartcli_core import PtySession
    from smartcli_core.pty_backend import IncompleteWrite

    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(REPO / "smartcli_core"):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2) from None


def _load_daemon(name: str, path: Path):
    """Import a fresh copy of tui.py (so a test can pin env at its import)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tui = _load_daemon("drive_tui", TUI_DIR / "tui.py")

TOKEN = "t0kentoken"


# --------------------------------------------------------------------------
# S6 — device-reply progress
# --------------------------------------------------------------------------


class ReplyTransport:
    """An injected transport that refuses a device reply, deterministically.

    ``land`` is how many bytes the transport claims the child accepted before it
    gave up (``None`` = "it cannot say"), ``fail_times`` how many writes raise
    first. Every attempt is recorded, so "the suffix was resumed exactly once"
    and "no byte was ever sent twice" are both readable off ``writes``/``on_wire``.
    """

    READ_BUDGET_CAPABLE = True

    def __init__(self, land=3, fail_times=1, query=b"\x1b[6n"):
        self.land = land
        self.fail_times = fail_times
        self.query = query
        self.writes: list[bytes] = []
        self.on_wire = bytearray()

    # -- PtyBackend surface ------------------------------------------------
    def spawn(self, cmd, cols, rows) -> None:
        pass

    def read_nonblocking(self) -> bytes:
        out, self.query = self.query, b""
        return out

    def _read_budgeted(self, max_bytes: int) -> bytes:
        return self.read_nonblocking()

    def read_status(self) -> dict:
        return {"readable_now": False, "eof": False, "error": None,
                "queued_payload_bytes": 0, "reader_held_payload_bytes": 0,
                "generation": 1}

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))
        if len(self.writes) <= self.fail_times:
            if self.land is not None:
                self.on_wire += bytes(data[:self.land])
            raise IncompleteWrite(self.land, len(data), "deadline before next write")
        self.on_wire += bytes(data)

    def resize(self, cols, rows) -> None:
        pass

    def is_alive(self) -> bool:
        return True

    def terminate(self) -> None:
        pass

    def close_state(self) -> dict:
        return {}


class ReplyProgress(unittest.TestCase):
    """S6: an owed reply is resumed on a later turn — and never duplicated."""

    def test_a_partial_reply_is_resumed_on_a_later_turn(self):
        backend = ReplyTransport(land=3, fail_times=1)
        sess = PtySession(backend=backend)
        sess.reply_retry_bytes = 64
        sess.pump(max_bytes=64)

        pending = sess.io_block()["pending"]
        self.assertEqual(len(backend.writes), 1, "one attempt per observation")
        owed = pending["reply_bytes"]
        self.assertGreater(owed, 0, "the unwritten suffix stays owed")
        self.assertTrue(pending["reply_error"], "and the reason stays visible")

        receipt = sess.retry_pending_reply()

        full = backend.writes[0]
        self.assertEqual(len(backend.writes), 2, "a later turn resumes the reply")
        self.assertEqual(backend.writes[1], full[3:],
                         "the SUFFIX goes on the wire, never the whole payload again")
        self.assertEqual(bytes(backend.on_wire), full,
                         "every byte exactly once, in the child's order")
        self.assertEqual(receipt["attempted"], owed)
        pending = sess.io_block()["pending"]
        self.assertEqual(pending["reply_bytes"], 0)
        self.assertIsNone(pending["reply_error"], "cleared only once nothing is owed")

    def test_the_retry_budget_bounds_the_extra_bytes(self):
        backend = ReplyTransport(land=0, fail_times=10_000)  # accepts nothing, always fails
        sess = PtySession(backend=backend)
        sess.reply_retry_bytes = 4
        sess.pump(max_bytes=64)
        self.assertEqual(len(backend.writes), 1, "the first attempt is unbudgeted (today's)")

        for _ in range(8):
            sess.retry_pending_reply()

        self.assertEqual(sum(len(w) for w in backend.writes[1:]), 4,
                         "the budget is counted in BYTES, not in attempts")
        before = len(backend.writes)
        sess.retry_pending_reply()
        self.assertEqual(len(backend.writes), before,
                         "once the budget is spent, retrying stops")
        self.assertGreater(sess.io_block()["pending"]["reply_bytes"], 0,
                           "the debt is still reported after the budget is gone")

    def test_without_a_budget_the_path_is_exactly_todays(self):
        backend = ReplyTransport(land=3, fail_times=10_000)
        sess = PtySession(backend=backend)         # reply_retry_bytes stays None
        sess.pump(max_bytes=64)
        for _ in range(3):
            sess.retry_pending_reply()
        self.assertEqual(len(backend.writes), 1,
                         "a session that declares no budget keeps one attempt per observation")
        pending = sess.io_block()["pending"]
        self.assertGreater(pending["reply_bytes"], 0)
        self.assertTrue(pending["reply_error"])

    def test_bytes_the_transport_cannot_account_for_are_never_re_sent(self):
        backend = ReplyTransport(land=None, fail_times=10_000)
        sess = PtySession(backend=backend)
        sess.reply_retry_bytes = 4096              # budget available, and deliberately unused
        sess.pump(max_bytes=64)
        owed = sess.io_block()["pending"]["reply_bytes"]
        self.assertEqual(owed, len(backend.writes[0]),
                         "unknown landing means the whole payload is owed")

        for _ in range(3):
            sess.retry_pending_reply()

        self.assertEqual(len(backend.writes), 1,
                         "bytes that may already be on the wire are never re-sent")
        self.assertEqual(sess.io_block()["pending"]["reply_bytes"], owed)

    def test_a_new_reply_is_queued_behind_the_owed_suffix(self):
        backend = ReplyTransport(land=3, fail_times=1)
        sess = PtySession(backend=backend)
        sess.reply_retry_bytes = 4096
        sess.pump(max_bytes=64)                    # reply A: 3 bytes landed, the rest is owed
        first = backend.writes[0]

        backend.query = b"\x1b[6n"                 # the child asks again
        sess.pump(max_bytes=64)                    # reply B

        suffix = first[3:]
        second = backend.writes[1]
        self.assertTrue(second.startswith(suffix),
                        "the owed suffix must go first: wire order is the child's order")
        self.assertEqual(bytes(backend.on_wire), first + second[len(suffix):])


class RetryingSession:
    """A session that declares the S6 retry surface."""

    def __init__(self):
        self.io_turn_bytes = tui.IO_TURN_BYTES
        self.calls: list[str] = []

    def pump(self, max_bytes=None):
        self.calls.append("pump")
        return b""

    def retry_pending_reply(self):
        self.calls.append("retry")


class PreS6Session:
    """A session object that predates the retry surface."""

    def __init__(self):
        self.io_turn_bytes = tui.IO_TURN_BYTES
        self.calls: list[str] = []

    def pump(self, max_bytes=None):
        self.calls.append("pump")
        return b""


class FakeListenSocket:
    """A listen socket whose accept() always times out (no peers, no ports)."""

    def settimeout(self, value) -> None:
        pass

    def accept(self):
        raise TimeoutError("no peer")

    def close(self) -> None:
        pass


class DaemonDrivesTheRetry(unittest.TestCase):
    """S6 needs a later TURN, and the daemon's worker owns those turns."""

    def run_daemon_for(self, sess, seconds: float):
        srv = FakeListenSocket()
        stop = threading.Event()
        caught: list[BaseException] = []

        def target():
            try:
                tui._serve_forever(srv, sess, TOKEN, stop)
            except BaseException as exc:      # pragma: no cover - reported below
                caught.append(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        time.sleep(seconds)
        stop.set()
        thread.join(timeout=5.0)
        return caught

    def test_a_service_turn_also_resumes_an_owed_reply(self):
        sess = RetryingSession()
        caught = self.run_daemon_for(sess, 0.7)
        self.assertEqual(caught, [], f"the accept loop raised: {caught}")
        self.assertIn("pump", sess.calls, "the transport is still serviced")
        self.assertIn("retry", sess.calls,
                      "every service turn must also give an owed reply its chance")

    def test_a_session_without_the_retry_surface_keeps_working(self):
        sess = PreS6Session()
        caught = self.run_daemon_for(sess, 0.7)
        self.assertEqual(caught, [], f"the accept loop raised: {caught}")
        self.assertTrue(sess.calls, "a pre-S6 session object is still serviced")


# --------------------------------------------------------------------------
# A05 / A06 — the daemon's own admission and reply bounds
# --------------------------------------------------------------------------


class FakeModel:
    def content_hash(self) -> int:
        return 1234

    def visual_hash(self) -> int:
        return 5678

    @property
    def alt_screen(self) -> bool:
        return False


class FakeSnapshot:
    def __init__(self, text: str = "fake"):
        self._text = text

    def to_text(self) -> str:
        return self._text

    def to_json(self, indent=None) -> str:
        return json.dumps({"text": self._text[:64], "alt_screen": False})


class ServiceSession:
    """A fake session for the daemon: fast verbs answer, one verb holds the worker."""

    def __init__(self, snapshot_text: str = "fake"):
        self.io_turn_bytes = tui.IO_TURN_BYTES
        self.model = FakeModel()
        self.snapshot_text = snapshot_text
        self.resizes: list[tuple[int, int]] = []
        self.working = threading.Event()    # set while the long wait owns the worker
        self.release = threading.Event()

    def pump(self, max_bytes=None) -> bytes:
        return b""

    def is_alive(self) -> bool:
        return True

    def snapshot(self):
        return FakeSnapshot(self.snapshot_text)

    def resize(self, cols: int, rows: int) -> None:
        self.resizes.append((cols, rows))

    def wait_for(self, *a, on_poll=None, **k):
        """A long wait that POLLS, exactly like the real one."""
        self.working.set()
        while not self.release.is_set():
            if on_poll is not None:
                on_poll()
            self.release.wait(0.02)
        return (False, FakeSnapshot(self.snapshot_text))


def start_daemon(sess):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((tui.HOST, 0))
    srv.listen(8)
    port = srv.getsockname()[1]
    stop = threading.Event()
    loop = threading.Thread(target=tui._serve_forever, args=(srv, sess, TOKEN, stop),
                            name="serve-loop", daemon=True)
    loop.start()
    time.sleep(0.2)
    return srv, port, stop, loop


def stop_daemon(srv, port, stop, loop):
    # `stop` is enough: the accept loop re-checks it every 0.2 s, and a wake-up
    # request would only leave an accepted connection for the exiting worker to
    # abandon.
    stop.set()
    loop.join(timeout=5.0)
    try:
        srv.close()
    except OSError:
        pass


def send_only(port, payload, timeout=5.0):
    """Send one request and hand back the socket WITHOUT waiting for the reply."""
    s = socket.create_connection((tui.HOST, port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    return s


def read_line(sock, timeout=3.0):
    sock.settimeout(timeout)
    buf = bytearray()
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf.extend(chunk)
    line = bytes(buf).split(b"\n", 1)[0]
    return json.loads(line.decode("utf-8")) if line else None


def request(port, payload, timeout=5.0):
    with send_only(port, payload, timeout) as s:
        return read_line(s, timeout)


class ReaderAdmission(unittest.TestCase):
    """A05: the reader cap must refuse at ADMISSION, not filter afterwards."""

    def test_a_connection_over_the_reader_cap_is_refused(self):
        old_cap, old_pre = tui.MAX_READERS, tui.PRE_AUTH_TIMEOUT
        tui.MAX_READERS, tui.PRE_AUTH_TIMEOUT = 2, 10.0
        sess = ServiceSession()
        srv, port, stop, loop = start_daemon(sess)
        held = []
        extra = None
        try:
            for _ in range(2):
                s = socket.create_connection((tui.HOST, port), timeout=5.0)
                s.sendall(b"{")           # valid start, never a newline: the slot is held
                held.append(s)
            time.sleep(0.3)
            extra = socket.create_connection((tui.HOST, port), timeout=5.0)
            refusal = read_line(extra, timeout=3.0)
        finally:
            if extra is not None:
                extra.close()
            for s in held:
                s.close()
            stop_daemon(srv, port, stop, loop)
            tui.MAX_READERS, tui.PRE_AUTH_TIMEOUT = old_cap, old_pre

        self.assertIsNotNone(refusal, "an over-cap connection must get an explicit refusal")
        self.assertFalse(refusal.get("ok"), refusal)
        self.assertEqual(refusal.get("reason"), "too_many_readers")
        self.assertTrue(refusal.get("error"), "the CLI/MCP surfaces print `error`")


class JobAdmission(unittest.TestCase):
    """A05: the job cap is real, explicit, and drops nothing."""

    def test_a_request_over_the_jobs_cap_is_refused_and_admitted_ones_run(self):
        old = tui.MAX_JOBS
        tui.MAX_JOBS = 2
        sess = ServiceSession()
        srv, port, stop, loop = start_daemon(sess)
        waiter = queued = extra = None
        try:
            waiter = send_only(port, {"token": TOKEN, "action": "wait_regex",
                                      "pattern": "never", "timeout_ms": 30000})
            self.assertTrue(sess.working.wait(timeout=5.0),
                            "the long wait must be owned by the worker")
            queued = [send_only(port, {"token": TOKEN, "action": "resize",
                                       "cols": 80, "rows": 24}) for _ in range(2)]
            time.sleep(0.2)
            extra = send_only(port, {"token": TOKEN, "action": "resize",
                                     "cols": 90, "rows": 30})
            refusal = read_line(extra, timeout=3.0)

            self.assertIsNotNone(refusal, "an over-cap request must get an explicit refusal")
            self.assertFalse(refusal.get("ok"), refusal)
            self.assertEqual(refusal.get("reason"), "too_many_jobs")
            self.assertEqual(sess.resizes, [], "the refused request was not executed")

            # Nothing was dropped: releasing the worker runs the admitted work.
            sess.release.set()
            replies = [read_line(s, timeout=5.0) for s in queued]
            for r in replies:
                self.assertTrue(r and r.get("ok"), r)
            self.assertEqual(sess.resizes, [(80, 24), (80, 24)],
                             "both admitted resizes ran once the worker freed up")
        finally:
            sess.release.set()
            for s in (waiter, extra, *(queued or [])):
                if s is not None:
                    s.close()
            stop_daemon(srv, port, stop, loop)
            tui.MAX_JOBS = old

    def test_a_caller_under_the_cap_is_served_exactly_as_before(self):
        sess = ServiceSession()
        srv, port, stop, loop = start_daemon(sess)
        try:
            reply = request(port, {"token": TOKEN, "action": "alive"})
            self.assertTrue(reply and reply.get("ok"), reply)
            reply = request(port, {"token": TOKEN, "action": "resize", "cols": 100, "rows": 30})
            self.assertTrue(reply and reply.get("ok"), reply)
            self.assertEqual(sess.resizes, [(100, 30)])
        finally:
            stop_daemon(srv, port, stop, loop)


class ScriptedConn:
    """A connection double for a peer that reads, or one that has stopped.

    Windows loopback has NO backpressure -- an 8 MB send into a 4 KB receive
    buffer completed in 1 ms, measured on this box -- so a real socket cannot model
    "the peer stopped reading" here. This double keeps exactly the parts the code
    under test uses:

      * ``fileno`` is a real socket, because ``select()`` on Windows accepts
        sockets only (a pipe fd fails with WinError 10038), so the deadline wait
        inside ``_reply`` is a real ``select()`` and not a patched one;
      * ``send`` reports EAGAIN forever when stalled, or hands over at most one
        buffer's worth of bytes otherwise, like a real socket;
      * ``sendall`` is the BLOCKING send the daemon used before A06 -- it returns
        only when the peer has taken everything, which for a stopped peer is never.
        It exists so this gate models what it claims to lock; the fix must not
        call it at all.

    ``recv`` replays a prepared request line for the reader thread.
    """

    def __init__(self, request: dict | None = None, stalled: bool = False,
                 chunk: int = 65536, pause: float = 0.0, blocking_hang: float = 60.0):
        self._sock, self._peer = socket.socketpair()
        self.stalled = stalled
        self.chunk = chunk
        self.pause = pause
        self.blocking_hang = blocking_hang
        self._request = (json.dumps(request) + "\n").encode("utf-8") if request else b""
        self.sent = bytearray()
        self.send_attempts = 0
        self.sendall_calls = 0
        self.closed = False
        self.first_send_at: float | None = None
        self._accept_at = 0.0

    # -- socket surface used by the daemon --------------------------------
    def settimeout(self, value) -> None:
        pass

    def setblocking(self, flag) -> None:
        pass

    def recv(self, n: int) -> bytes:
        out, self._request = bytes(self._request[:n]), self._request[n:]
        return out

    def send(self, data) -> int:
        self.send_attempts += 1
        if self.first_send_at is None:
            self.first_send_at = time.monotonic()
        if self.stalled:
            raise BlockingIOError(10035, "injected: the peer stopped reading")
        if self.pause and time.monotonic() < self._accept_at:
            # A peer that IS reading but drains slowly: it takes the next slice only
            # after `pause`. Progress, just not instant -- the distinction A06's
            # stall window has to make.
            raise BlockingIOError(10035, "injected: the peer is draining slowly")
        count = min(len(data), self.chunk)
        self.sent += bytes(data[:count])
        if self.pause:
            self._accept_at = time.monotonic() + self.pause
        return count

    def sendall(self, data) -> None:
        self.sendall_calls += 1
        self.first_send_at = time.monotonic()
        if self.stalled:
            time.sleep(self.blocking_hang)
        self.sent += bytes(data)

    def fileno(self) -> int:
        return self._sock.fileno()

    def close(self) -> None:
        self.closed = True
        for sock in (self._sock, self._peer):
            try:
                sock.close()
            except OSError:
                pass

    def reply(self):
        """The reply this peer received, decoded (None when nothing arrived)."""
        line = bytes(self.sent).split(b"\n", 1)[0]
        return json.loads(line.decode("utf-8")) if line else None


class ScriptedListen:
    """A listen socket that hands out prepared connections in accept() order."""

    def __init__(self, conns):
        self._pending = list(conns)
        self.accepted = 0

    def settimeout(self, value) -> None:
        pass

    def accept(self):
        if not self._pending:
            raise TimeoutError("no peer")
        self.accepted += 1
        return self._pending.pop(0), ("127.0.0.1", 0)

    def close(self) -> None:
        pass


class BoundedReply(unittest.TestCase):
    """A06: a peer that stops reading must not hold the sender."""

    def test_a_peer_that_stops_reading_is_released_inside_the_stall_window(self):
        conn = ScriptedConn(stalled=True)
        payload = {"ok": True, "text": "x" * 1_000_000}
        try:
            t0 = time.monotonic()
            # A LONG ceiling with a short stall window: what releases the sender must
            # be "the peer accepted nothing for N", not "the total budget ran out".
            receipt = tui._reply(conn, payload, deadline=10.0, stall=0.3)
            elapsed = time.monotonic() - t0
        finally:
            conn.close()

        self.assertFalse(receipt["sent"], f"a stalled send is reported, not assumed: {receipt}")
        self.assertEqual(receipt["bytes"], 0)
        self.assertEqual(receipt["deadline_s"], 10.0)
        self.assertGreaterEqual(receipt["total_bytes"], 1_000_000)
        self.assertIn("stalled", receipt["reason"] or "")
        self.assertGreaterEqual(conn.send_attempts, 2,
                                "the send must be retried on the wait, not attempted once")
        self.assertLess(elapsed, 1.5, f"the stall window must bound the call, took {elapsed:.2f}s")

    def test_a_slow_but_progressing_peer_keeps_its_patience(self):
        # THE control for the test above, and the reason A06 is a stall window and
        # not a shorter ceiling: this peer is slow -- the whole transfer takes longer
        # than the stall window -- but every accepted slice RENEWS the window, so it
        # must receive the entire reply. A naive "abandon after N seconds" fails here.
        window = 0.3
        conn = ScriptedConn(chunk=32768, pause=0.08)
        payload = {"ok": True, "text": "y" * 500_000}
        try:
            t0 = time.monotonic()
            receipt = tui._reply(conn, payload, deadline=30.0, stall=window)
            elapsed = time.monotonic() - t0
        finally:
            conn.close()

        self.assertTrue(receipt["sent"], receipt)
        self.assertEqual(receipt["bytes"], receipt["total_bytes"])
        self.assertGreater(elapsed, window,
                           "the transfer must outlast the stall window, or this proves nothing")
        self.assertLess(elapsed, receipt["deadline_s"])
        self.assertGreater(conn.send_attempts, 1, "the payload spanned several slices")
        self.assertEqual(conn.reply(), payload)

    def test_a_healthy_peer_still_receives_the_whole_payload(self):
        # Bounding the send must not truncate a legitimate reply, and the suffix
        # retry must not duplicate it. `chunk` forces several partial sends, which is
        # the path a real socket takes for a payload larger than one buffer.
        conn = ScriptedConn(chunk=65536)
        payload = {"ok": True, "text": "y" * 500_000}
        try:
            receipt = tui._reply(conn, payload, deadline=5.0)
        finally:
            conn.close()

        self.assertTrue(receipt["sent"], receipt)
        self.assertEqual(receipt["bytes"], receipt["total_bytes"])
        self.assertGreater(conn.send_attempts, 1, "the payload spanned several sends")
        self.assertEqual(conn.reply(), payload)

    def test_the_healthy_path_keeps_todays_ceiling(self):
        # A06 must not shorten what a reading caller gets: the default ceiling is
        # still 60 s (this file does not pin SMARTCLI_REPLY_TIMEOUT_MS), while the
        # no-progress window is the small one this file pinned.
        conn = ScriptedConn(chunk=65536)
        try:
            receipt = tui._reply(conn, {"ok": True, "text": "tiny"})
        finally:
            conn.close()
        self.assertTrue(receipt["sent"], receipt)
        self.assertEqual(receipt["deadline_s"], 60.0)
        self.assertEqual(receipt["stall_s"], 0.4)

    def test_the_worker_serves_another_caller_while_a_reply_is_stalled(self):
        # The session's ONLY worker sends A's reply first; A has stopped reading.
        # B's request must still be answered, and the gap between the two tells us
        # it queued behind the abandoned send instead of taking a fast path.
        stalled = ScriptedConn(request={"token": TOKEN, "action": "snapshot"}, stalled=True)
        healthy = ScriptedConn(request={"token": TOKEN, "action": "alive"})
        sess = ServiceSession(snapshot_text="z" * 64)
        stop = threading.Event()
        loop = threading.Thread(target=tui._serve_forever,
                                args=(ScriptedListen([stalled, healthy]), sess, TOKEN, stop),
                                name="serve-loop", daemon=True)
        loop.start()
        try:
            deadline = time.monotonic() + 5.0
            while healthy.first_send_at is None and time.monotonic() < deadline:
                time.sleep(0.02)
        finally:
            stop.set()
            loop.join(timeout=5.0)

        self.assertIsNotNone(healthy.first_send_at, "the second caller was never answered")
        self.assertTrue(healthy.reply() and healthy.reply().get("ok"), healthy.reply())
        self.assertEqual(stalled.sendall_calls, 0,
                         "the blocking send must not be used at all")
        self.assertGreater(stalled.send_attempts, 0)
        gap = healthy.first_send_at - stalled.first_send_at
        self.assertGreaterEqual(gap, tui.REPLY_STALL_SECONDS * 0.5,
                                "the second caller must have queued behind the stalled reply, "
                                "or this measured a fast path")
        self.assertLess(gap, 2.0, f"a stalled peer held the worker for {gap:.2f}s")
        stalled.close()
        healthy.close()


class BudgetsComeFromTheEnvironment(unittest.TestCase):
    """A05/A06/S6 budgets are operator-tunable, and default conservatively."""

    def test_the_bounds_and_the_caps_come_from_the_environment(self):
        with mock.patch.dict(os.environ, {
            "SMARTCLI_REPLY_TIMEOUT_MS": "45000",
            "SMARTCLI_REPLY_STALL_SECONDS": "1.5",
            "SMARTCLI_MAX_READERS": "7",
            "SMARTCLI_MAX_JOBS": "9",
            "SMARTCLI_REPLY_RETRY_BYTES": "128",
        }):
            mod = _load_daemon("drive_tui_envcheck", TUI_DIR / "tui.py")
        self.assertEqual(mod.POST_AUTH_TIMEOUT, 45.0)
        self.assertEqual(mod.REPLY_STALL_SECONDS, 1.5)
        self.assertEqual(mod.MAX_READERS, 7)
        self.assertEqual(mod.MAX_JOBS, 9)
        self.assertEqual(mod.REPLY_RETRY_BYTES, 128)

    def test_the_s6_retry_defaults_to_todays_behaviour(self):
        # The budget is opt-in: unset means "one attempt per observation", exactly
        # what every pre-S6 caller already relies on.
        mod = _load_daemon("drive_tui_defaults", TUI_DIR / "tui.py")
        self.assertEqual(mod.REPLY_RETRY_BYTES, 0)
        sess = PtySession(backend=ReplyTransport(land=3, fail_times=10_000))
        self.assertIsNone(getattr(sess, "reply_retry_bytes", None))

    def test_the_a06_defaults_are_a_small_stall_inside_the_old_ceiling(self):
        # Guards the rig and the policy at once: this file pinned only the stall
        # window, so the ceiling the daemon module sees must still be the pre-A06
        # 60 s, with the small window inside it.
        self.assertAlmostEqual(tui.REPLY_STALL_SECONDS, 0.4)
        self.assertAlmostEqual(tui.POST_AUTH_TIMEOUT, 60.0)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
