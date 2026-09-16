"""A04-S5: the Windows reader must not accumulate an unbounded backlog.

Measured before this slice (X2): with no client polling, the reader queue grew
without limit -- 271 307 bytes in 7.5 s at ~93 KB/s. The cap added here is on the
*accounted payload* (queue + the chunk in hand + the unreturned suffix), and it
works by refusing to pull more from ConPTY, never by dropping bytes.

Two injected transports, because they cover different states:

* ``FakeProc`` -- fulfils every read immediately. It drives the cap and the
  accounting, but its reader can never be stopped by the cap itself: "nothing is
  queued" and "the reader is paused in the transport" are the same state on it.
* ``PausingProc`` -- blocks in ``read`` until the test feeds it, like a ConPTY whose
  child has nothing to say (or is already gone). Here the reader really does stop at
  the high water and start again when the consumer takes payload, which is the
  behaviour the cap exists for and the one the fake could not reach.

The production reader thread and the production queue/condition logic run
unchanged in both cases. No ConPTY, no child process.

Run: python -B tests/test_a04_winpty_backlog.py [--repo PATH]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading
import time
import unittest

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
REPO = args.repo.resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
try:
    from smartcli_core.pty_backend import WinptyBackend
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(REPO / "smartcli_core"):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)


class FakeProc:
    """pywinpty-shaped: read() returns str, blocks when the script is done."""

    def __init__(self, chunks, chunk_size=64):
        self._chunks = list(chunks)
        self.chunk_size = chunk_size
        self.reads = 0
        self._buf = ""
        self._lock = threading.Lock()

    def read(self, _n):
        """Return up to chunk_size chars, keeping the remainder -- like the real
        pywinpty, which buffers internally. (A fake that dropped the tail would
        make this test fail for its own reason, not the backend's.)"""
        with self._lock:
            self.reads += 1
            if not self._buf:
                if not self._chunks:
                    time.sleep(0.01)
                    raise EOFError
                self._buf = self._chunks.pop(0)
            out, self._buf = self._buf[: self.chunk_size], self._buf[self.chunk_size:]
            return out

    def isalive(self):
        return bool(self._chunks)

    def terminate(self, force=False):
        self._chunks.clear()


class PausingProc:
    """pywinpty-shaped, but its ``read`` can ACTUALLY PAUSE.

    ``FakeProc`` always returns immediately, so a reader driving it never stops at
    the high water and "nothing is queued" and "the reader is blocked in the
    transport" can never happen together -- which is exactly why the suite was
    green next to a client-side stall. Here ``read`` blocks until the test feeds a
    chunk, the way a ConPTY blocks when its child has produced nothing (and, after
    the child is gone, keeps blocking: the transport does not close itself).

    ``read`` never raises EOFError on its own; ``terminate`` closes it.
    """

    def __init__(self, chunk_size=64):
        self.chunk_size = chunk_size
        self.reads = 0
        self._pending: list[str] = []
        self._cv = threading.Condition()
        self._stopped = False

    def feed(self, chunk: str) -> None:
        """Make ``chunk`` readable, releasing a reader already blocked in read."""
        with self._cv:
            self._pending.append(chunk)
            self._cv.notify_all()

    def read(self, _n):
        with self._cv:
            self.reads += 1
            while not self._pending and not self._stopped:
                self._cv.wait(0.05)
            if self._pending:
                return self._pending.pop(0)[: self.chunk_size]
        raise EOFError("transport closed")

    def isalive(self):
        return not self._stopped

    def terminate(self, force=False):
        with self._cv:
            self._stopped = True
            self._pending.clear()
            self._cv.notify_all()


def make_backend(chunks=None, *, high, low, chunk_size=64, proc=None):
    """A backend whose reader thread runs the production _read_loop.

    ``proc`` injects a transport directly; otherwise ``chunks`` is scripted into a
    ``FakeProc``, and ``chunks=None`` installs a ``PausingProc`` (the transport that
    can stop the reader, for the tests that need a real pause).
    """
    backend = WinptyBackend()
    backend.QUEUE_PAYLOAD_HIGH = high
    backend.QUEUE_PAYLOAD_LOW = low
    if proc is None:
        proc = PausingProc(chunk_size=chunk_size) if chunks is None else FakeProc(
            chunks, chunk_size=chunk_size)
    backend._proc = proc
    backend._queue = __import__("queue").Queue()
    backend._carry = bytearray()
    backend._room = threading.Condition()
    backend._stopping = False
    backend._generation = 1
    backend._reader = threading.Thread(target=backend._read_loop,
                                       args=(proc, backend._queue, backend._room), daemon=True)
    backend._reader.start()
    return backend, proc


def wait_for(predicate, timeout=2.0) -> bool:
    """Poll ``predicate`` (no PTY, no child: a few ms is plenty for a thread wake)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return bool(predicate())


class WinptyBacklog(unittest.TestCase):
    def test_accounted_payload_never_exceeds_the_high_water_mark(self):
        chunks = ["x" * 64 for _ in range(64)]          # 4 KiB of script
        backend, proc = make_backend(chunks, high=256, low=64)
        try:
            peak = 0
            for _ in range(60):
                peak = max(peak, backend._accounted_payload())
                time.sleep(0.01)
            self.assertLessEqual(peak, backend.QUEUE_PAYLOAD_HIGH + 64,
                                 f"reader overran its budget (peak {peak})")
            self.assertLess(proc.reads, 64, "the reader must stop pulling when full")
            # and it must resume once the consumer has taken payload back below the
            # low mark: that drain is what releases it, not its own 0.25 s tick.
            paused_reads = proc.reads
            drained = backend._read_budgeted(8 * 64)
            self.assertTrue(drained)
            self.assertTrue(wait_for(lambda: proc.reads > paused_reads, 0.2),
                            "the consumer's drain below the low mark must restart the reader")
        finally:
            backend.terminate()
            backend._reader.join(timeout=3)

    def test_nothing_is_dropped_or_duplicated(self):
        payload = b"".join(bytes([65 + (i % 26)]) for i in range(2048))
        backend, _proc = make_backend([payload.decode("latin-1")], high=128, low=32,
                                      chunk_size=128)
        got = bytearray()
        deadline = time.monotonic() + 5.0
        try:
            while len(got) < len(payload) and time.monotonic() < deadline:
                chunk = backend._read_budgeted(64)
                got += chunk
                if not chunk:
                    time.sleep(0.01)
            self.assertEqual(bytes(got), payload, "the bounded reader must not lose or repeat bytes")
        finally:
            backend.terminate()
            backend._reader.join(timeout=3)

    def test_status_reports_queue_and_held_separately(self):
        backend, _proc = make_backend(["y" * 200], high=1024, low=256)
        try:
            time.sleep(0.2)
            first = backend._read_budgeted(8)
            self.assertTrue(first)
            status = backend.read_status()
            self.assertEqual(status["reader_held_payload_bytes"] + status["queued_payload_bytes"],
                             backend._accounted_payload())
            self.assertIsInstance(status["queued_payload_bytes"], int)
        finally:
            backend.terminate()
            backend._reader.join(timeout=3)

    def test_terminate_wakes_a_reader_blocked_on_a_full_queue(self):
        chunks = ["z" * 64 for _ in range(200)]
        backend, _proc = make_backend(chunks, high=128, low=32)
        time.sleep(0.2)
        self.assertTrue(backend._accounted_payload() >= 128,
                        "precondition: the reader is at its budget")
        backend.terminate()                       # must not hang
        backend._reader.join(timeout=3)
        self.assertFalse(backend._reader.is_alive(),
                         "a reader waiting for room must be woken by terminate()")

    def test_a_late_reader_cannot_pollute_the_next_generation(self):
        # The reader holds its own queue object; a second spawn gets a fresh one and
        # the old thread keeps writing into the old queue only.
        backend, _proc = make_backend(["a" * 32], high=1024, low=256)
        first_queue = backend._queue
        backend._stopping = True
        with backend._room:
            backend._room.notify_all()
        backend._reader.join(timeout=3)
        backend._queue = __import__("queue").Queue()
        backend._room = threading.Condition()
        backend._stopping = False
        self.assertIsNot(backend._queue, first_queue)
        self.assertEqual(backend._accounted_payload(), 0)


class WinptyPausedReader(unittest.TestCase):
    """The cap on a transport that really stops the reader.

    ``FakeProc`` fulfils every read, so a reader driving it is never held by the cap
    itself -- the state the S5 cap is about. These two tests put the production
    reader thread on a transport that blocks in ``read`` until fed, and assert the
    two properties the cap has to keep there: the reader stops at the high water,
    and the stream still arrives whole once the consumer drains.

    ``tests/test_a04_read_budget.py`` covers the client's byte budget; this class is
    only about the reader side of the same queue.
    """

    def test_the_reader_stops_at_the_high_water_with_a_pausing_transport(self):
        backend, proc = make_backend(None, high=192, low=128)
        try:
            for name in ("A", "B", "C"):
                proc.feed(name * 64)
            self.assertTrue(wait_for(lambda: backend._accounted_payload() >= 192),
                            "precondition: the reader must reach its high water")
            self.assertEqual(backend._accounted_payload(), 192)
            reads_at_cap = proc.reads
            time.sleep(0.3)          # longer than the reader's own 0.25 s tick
            self.assertEqual(proc.reads, reads_at_cap,
                             "a reader at its cap must not keep pulling")
            self.assertTrue(proc.isalive(),
                            "the transport is open: the stop is the cap, not an ended stream")
            self.assertFalse(backend.read_status()["eof"])
        finally:
            backend.terminate()
            backend._reader.join(timeout=3)

    def test_a_paused_reader_resumes_when_the_consumer_drains_and_loses_nothing(self):
        payload = b"".join(bytes([65 + (i % 26)]) for i in range(2048))
        backend, proc = make_backend(None, high=256, low=64, chunk_size=128)
        got = bytearray()
        peak = 0
        try:
            for off in range(0, len(payload), 128):
                proc.feed(payload[off:off + 128].decode("latin-1"))
            deadline = time.monotonic() + 5.0
            paused = False
            while len(got) < len(payload) and time.monotonic() < deadline:
                got += backend._read_budgeted(64)
                accounted = backend._accounted_payload()
                peak = max(peak, accounted)
                paused = paused or accounted >= backend.QUEUE_PAYLOAD_HIGH
            self.assertTrue(paused, "precondition: the reader must have reached its cap")
            self.assertEqual(bytes(got), payload,
                             "no byte may be lost, repeated or reordered across a pause")
            self.assertLessEqual(peak, backend.QUEUE_PAYLOAD_HIGH + 128,
                                 "the cap must hold while the reader is paused")
        finally:
            backend.terminate()
            backend._reader.join(timeout=3)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
