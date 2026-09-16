"""N2: scheduling edges of the write path that the 256 KiB test never reached.

The T03 real-pty test proved "every byte, exactly once" for one long write. It did
not exercise three narrower paths, and all three are reachable from a real daemon:

  * a trickling writer that returns ONE POSITIVE BYTE per call forever -- the
    offset advances on every call, so a loop that only checks its deadline in the
    EAGAIN/EINTR/zero-progress branches can run past the deadline unnoticed;
  * ``select.select`` itself raising (it is a syscall: EINTR, EBADF, a signal);
    the bytes already written must still appear in the receipt;
  * a device reply that fails or fails partially -- perception must keep working,
    the failure must be VISIBLE (not swallowed), and the unwritten suffix must not
    turn into a duplicate reply on the next pump.

Injected transport only: no PTY, no child process, ≤4096 B payloads, ≤1000
injected calls, and a fake clock so every deadline case is deterministic.

Run: python -B tests/test_partial_write_edges.py [--repo PATH]
"""
from __future__ import annotations

import argparse
import errno
import os
from pathlib import Path
import select
import sys
import time
import unittest
from unittest.mock import patch

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
REPO = args.repo.resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
try:
    from smartcli_core import PtySession
    from smartcli_core.pty_backend import IncompleteWrite, PosixPtyBackend
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(REPO / "smartcli_core"):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)

PAYLOAD = bytes(range(64))
FAKE_FD = 424242


class SteppingClock:
    """monotonic() that advances a fixed step per call (deterministic deadlines)."""

    def __init__(self, step=0.02):
        self.step, self.t = step, 0.0

    def __call__(self):
        value = self.t
        self.t += self.step
        return value


class Trickle:
    """os.write that accepts exactly one byte per call, forever."""

    def __init__(self, payload=PAYLOAD):
        self.payload = payload
        self.calls = 0
        self.received = bytearray()

    def __call__(self, fd, data):
        assert fd == FAKE_FD
        self.calls += 1
        if self.calls > 1000:
            raise RuntimeError("injected-call budget exceeded -- the loop is unbounded")
        self.received += bytes(data[:1])
        return 1


class WriteEdges(unittest.TestCase):
    def run_write(self, writer, *, waiter=None, timeout=0.05, step=0.02, payload=PAYLOAD):
        backend = PosixPtyBackend()
        backend._fd = FAKE_FD
        backend.write_timeout = timeout
        errors = []
        clock = SteppingClock(step)
        patches = [patch.object(os, "write", writer)]
        if waiter is not None:
            patches.append(patch.object(select, "select", waiter))
        try:
            with patches[0], (patches[1] if waiter is not None else patch.object(select, "select",
                                                                                lambda *a, **k: ([], [FAKE_FD], []))):
                with patch.object(time, "monotonic", clock):
                    backend.write(payload)
        except Exception as exc:                     # noqa: BLE001 - the receipt is the point
            errors.append(exc)
        finally:
            backend._fd = None
        return writer, errors

    def test_trickling_writer_still_honours_the_deadline(self):
        # Every call makes progress, so a deadline check placed only in the
        # no-progress branches never fires: 64 one-byte calls run to completion
        # even though the deadline passed after the third.
        writer, errors = self.run_write(Trickle())
        if not errors:
            self.fail("a trickling writer ran past the deadline and still reported success "
                      f"({writer.calls} calls, {len(writer.received)}/{len(PAYLOAD)} bytes)")
        err = errors[0]
        self.assertIsInstance(err, IncompleteWrite)
        self.assertEqual(err.total_bytes, len(PAYLOAD))
        self.assertEqual(err.written_bytes, len(writer.received),
                         "the receipt must state exactly what landed")
        self.assertIn("deadline", err.reason)
        self.assertLessEqual(err.written_bytes, len(PAYLOAD))

    def test_a_write_that_finishes_before_the_deadline_is_not_downgraded(self):
        # Control for the check above: completion must stay completion.
        writer, errors = self.run_write(Trickle(payload=b"abc"), timeout=5.0, payload=b"abc")
        self.assertEqual(errors, [])
        self.assertEqual(bytes(writer.received), b"abc")

    def test_select_oserror_keeps_the_written_prefix(self):
        def boom(reads, writes, errors_, timeout=None):
            raise OSError(errno.EBADF, "injected select failure")

        class First(Trickle):
            def __call__(self, fd, data):
                if self.calls == 0:
                    self.calls += 1
                    self.received += bytes(data[:3])
                    return 3
                # the next call must never happen: EAGAIN first, then select fails
                raise BlockingIOError(errno.EAGAIN, "injected")

        writer, errors = self.run_write(First(), waiter=boom, timeout=5.0)
        self.assertTrue(errors, "a select() failure must surface, not be swallowed")
        err = errors[0]
        self.assertIsInstance(err, IncompleteWrite)
        self.assertEqual(err.written_bytes, 3,
                         "the three bytes that already landed must appear in the receipt")
        self.assertIn("select", err.reason)

    def test_select_interrupt_retries_the_same_suffix(self):
        state = {"waits": 0}

        def interrupted_once(reads, writes, errors_, timeout=None):
            state["waits"] += 1
            if state["waits"] == 1:
                raise InterruptedError(errno.EINTR, "injected")
            return [], [FAKE_FD], []

        class ShortThenRest(Trickle):
            def __call__(self, fd, data):
                self.calls += 1
                if self.calls == 1:
                    raise BlockingIOError(errno.EAGAIN, "injected")
                n = min(7, len(data))
                self.received += bytes(data[:n])
                return n

        writer, errors = self.run_write(ShortThenRest(), waiter=interrupted_once, timeout=5.0)
        self.assertEqual(errors, [], f"an interrupted wait must be retried, got {errors}")
        self.assertEqual(bytes(writer.received), PAYLOAD, "no byte lost or duplicated")


class ReplyEdges(unittest.TestCase):
    """A device reply that cannot be written must be visible, not swallowed."""

    class Backend:
        READ_BUDGET_CAPABLE = True

        def __init__(self, reply_error=None, reply_partial=0):
            self.reply_error = reply_error
            self.reply_partial = reply_partial
            self.writes = []
            self._first = True
            self.data = b"\x1b[6n"      # a CPR query: pyte will answer it

        def spawn(self, *a, **k):
            pass

        def read_nonblocking(self):
            out, self.data = self.data, b""
            return out

        def _read_budgeted(self, max_bytes):
            return self.read_nonblocking()

        def read_status(self):
            return {"readable_now": False, "eof": False, "error": None,
                    "queued_payload_bytes": 0, "reader_held_payload_bytes": 0,
                    "generation": 1}

        def write(self, data):
            self.writes.append(bytes(data))
            if self.reply_error is not None:
                raise IncompleteWrite(self.reply_partial, len(data), self.reply_error)

        def resize(self, *a):
            pass

        def is_alive(self):
            return True

        def terminate(self):
            pass

        def close_state(self):
            return {}

    def test_a_failed_reply_is_recorded_not_swallowed(self):
        backend = self.Backend(reply_error="deadline", reply_partial=3)
        sess = PtySession(backend=backend)
        sess.pump(max_bytes=64)
        io = sess.io_block()
        pending = io["pending"]
        self.assertTrue(pending.get("reply_error"),
                        "a reply that could not be written must be reported")
        self.assertIn("3/", pending["reply_error"], "the known prefix must be in the receipt")
        self.assertEqual(len(backend.writes), 1, "the reply is attempted once, not retried blindly")
        self.assertGreater(pending["reply_bytes"], 0,
                           "the unwritten suffix stays accounted as pending")

    def test_a_failed_reply_is_not_duplicated_on_the_next_pump(self):
        backend = self.Backend(reply_error="deadline", reply_partial=3)
        sess = PtySession(backend=backend)
        sess.pump(max_bytes=64)
        first = list(backend.writes)
        backend.data = b""                    # nothing new to feed
        sess.pump(max_bytes=64)
        self.assertEqual(list(backend.writes), first,
                         "the runtime must not blindly re-send a reply it could not write")

    def test_a_healthy_reply_clears_the_state(self):
        backend = self.Backend()
        sess = PtySession(backend=backend)
        sess.pump(max_bytes=64)
        io = sess.io_block()
        self.assertIsNone(io["pending"].get("reply_error"))
        self.assertEqual(io["pending"]["reply_bytes"], 0)
        self.assertTrue(backend.writes, "the reply really was written")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
