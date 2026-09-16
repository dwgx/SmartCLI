"""T03 regression: a partial PTY write must never be reported as success.

The POSIX backend writes to a NON-BLOCKING master fd, so one ``os.write`` may
accept only a prefix, raise ``EAGAIN``, or be interrupted. The old code called
``os.write`` once and discarded its return value: the caller was told the input
had been sent while the child received a fraction of it.

These tests drive the REAL production method with an injected ``os.write`` and
``select.select``. That makes them fault-injection tests on real library code --
``E3 + injected os.write`` -- and NOT native-transport evidence: no PTY, no
child process, no kernel buffer is involved here, and a short write that a real
pty would perform is not reproduced. Native POSIX verification stays NOT_RUN.

Run: python tests/test_partial_write_regression.py [--repo PATH]
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
sys.dont_write_bytecode = True
sys.path.insert(0, str(args.repo.resolve()))
try:
    from smartcli_core.pty_backend import IncompleteWrite, PosixPtyBackend
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(
            (args.repo.resolve() / "smartcli_core")):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)

PAYLOAD = "A中\x00B\r\n保存".encode("utf-8")
FAKE_FD = 987654


class Recorder:
    """Injected transport: a scripted schedule of os.write outcomes."""

    def __init__(self, schedule, *, wait_budget=64, write_budget=64):
        self.schedule = list(schedule)
        self.received = bytearray()
        self.calls = 0
        self.waits = 0
        self.write_budget = write_budget
        self.wait_budget = wait_budget

    def write(self, fd, data):
        if fd != FAKE_FD:
            raise OSError(errno.EBADF, "fixture refuses unrelated fd")
        self.calls += 1
        if self.calls > self.write_budget:
            raise RuntimeError(f"write-attempt budget exceeded ({self.calls}) -- busy loop?")
        action = self.schedule[self.calls - 1] if self.calls <= len(self.schedule) else len(data)
        if action == "again":
            raise BlockingIOError(errno.EAGAIN, "injected")
        if action == "intr":
            raise InterruptedError(errno.EINTR, "injected")
        if action == "zero":
            return 0
        if isinstance(action, str) and action.startswith("error:"):
            code = getattr(errno, action.split(":", 1)[1])
            raise OSError(code, "injected failure")
        n = min(int(action), len(data))
        self.received.extend(bytes(data[:n]))
        return n

    def wait(self, reads, writes, errors, timeout=None):
        if any(f != FAKE_FD for f in [*reads, *writes, *errors]):
            raise RuntimeError("unexpected descriptor in select()")
        self.waits += 1
        if self.waits > self.wait_budget:
            raise RuntimeError(f"writable-wait budget exceeded ({self.waits}) -- busy loop?")
        return [], list(writes), []


def run_write(schedule, payload=PAYLOAD, *, write_timeout=None, clock=None, **kw):
    """Call the production method; return (recorder, error_or_None).

    ``clock`` replaces ``time.monotonic`` so a deadline can be reached in a few
    deterministic iterations instead of by burning real milliseconds (a fake
    clock also makes the test prove the loop re-checks the deadline rather than
    merely running out of wall time).
    """
    rec = Recorder(schedule, **kw)
    backend = PosixPtyBackend()
    backend._fd = FAKE_FD
    if write_timeout is not None:
        backend.write_timeout = write_timeout
    error = None
    try:
        with patch.object(os, "write", rec.write), patch.object(select, "select", rec.wait):
            if clock is not None:
                with patch.object(time, "monotonic", clock):
                    backend.write(payload)
            else:
                backend.write(payload)
    except Exception as exc:            # noqa: BLE001 - the receipt is the point
        error = exc
    finally:
        backend._fd = None
    return rec, error


def stepping_clock(step=0.02):
    """monotonic() that advances a fixed step on every call."""
    state = {"t": 0.0}

    def now():
        value = state["t"]
        state["t"] += step
        return value

    return now


class PartialWriteRegression(unittest.TestCase):
    # -- the transport delivers every byte exactly once, in order -----------
    def test_short_writes_only(self):
        rec, error = run_write([2, 1, 2])
        self.assertIsNone(error)
        self.assertEqual(bytes(rec.received), PAYLOAD, "every byte once, in order")
        self.assertGreater(rec.calls, 1)

    def test_short_write_eagain_eintr(self):
        rec, error = run_write([2, "again", "intr", 1])
        self.assertIsNone(error)
        self.assertEqual(bytes(rec.received), PAYLOAD)
        self.assertGreaterEqual(rec.waits, 1, "EAGAIN must wait for writability")

    def test_each_byte_at_a_time(self):
        rec, error = run_write([1] * (len(PAYLOAD) - 1))
        self.assertIsNone(error)
        self.assertEqual(bytes(rec.received), PAYLOAD)
        self.assertEqual(rec.calls, len(PAYLOAD))

    def test_zero_progress_is_not_treated_as_completion(self):
        rec, error = run_write(["zero", "zero", 3])
        self.assertIsNone(error)
        self.assertEqual(bytes(rec.received), PAYLOAD)
        self.assertGreaterEqual(rec.waits, 2)

    def test_empty_payload_is_a_noop(self):
        rec, error = run_write([], payload=b"")
        self.assertIsNone(error)
        self.assertEqual(bytes(rec.received), b"")
        self.assertEqual(rec.calls, 0, "an empty payload must not touch the transport")

    # -- failures carry the progress instead of claiming success ------------
    def test_deadline_reports_zero_progress_partial(self):
        # A fake clock reaches the deadline in a few iterations, so the loop is
        # proven to re-check it instead of spinning until real time passes.
        rec, error = run_write(["again"] * 16, write_timeout=0.05,
                               clock=stepping_clock(0.02))
        self.assertIsInstance(error, IncompleteWrite)
        self.assertEqual(error.written_bytes, 0)
        self.assertEqual(error.total_bytes, len(PAYLOAD))
        self.assertIn("deadline", error.reason)
        self.assertIsInstance(error, OSError, "existing OSError handlers must keep working")
        self.assertLessEqual(rec.calls, 6, "the deadline must end the loop, not a spin")

    def test_partial_then_error_reports_the_prefix_that_landed(self):
        rec, error = run_write([3, "error:EPIPE"])
        self.assertIsInstance(error, IncompleteWrite)
        self.assertEqual(error.written_bytes, 3)
        self.assertEqual(bytes(rec.received), PAYLOAD[:3])
        self.assertIn("BrokenPipeError", error.reason, "the failure keeps its origin")

    def test_bad_descriptor_is_a_zero_progress_error(self):
        rec, error = run_write(["error:EBADF"])
        self.assertIsInstance(error, IncompleteWrite)
        self.assertEqual(error.written_bytes, 0)
        self.assertEqual(bytes(rec.received), b"")

    def test_repeated_call_after_a_failure_is_not_sticky(self):
        rec1, error1 = run_write([3, "error:EIO"])
        self.assertIsInstance(error1, IncompleteWrite)
        rec2, error2 = run_write([2, 1])
        self.assertIsNone(error2, "a previous failure must not poison the next write")
        self.assertEqual(bytes(rec2.received), PAYLOAD)

    # -- the linearization point: the last accepted byte is the truth -------
    def test_completion_is_not_undone_by_a_later_deadline(self):
        # The final write lands and returns; the deadline is checked only while
        # bytes are still outstanding, so a finished request stays finished.
        rec, error = run_write([len(PAYLOAD)], write_timeout=0.000001)
        self.assertIsNone(error)
        self.assertEqual(bytes(rec.received), PAYLOAD)

    def test_no_bytes_are_resent_after_eagain(self):
        # The EAGAIN path must re-offer only the UNSENT suffix: a whole-payload
        # retry would duplicate the prefix in the child's input.
        rec, error = run_write([5, "again", "intr", 2])
        self.assertIsNone(error)
        self.assertEqual(bytes(rec.received), PAYLOAD)
        self.assertEqual(len(rec.received), len(PAYLOAD), "no duplicated bytes")

    def test_write_before_spawn_still_raises(self):
        backend = PosixPtyBackend()
        with self.assertRaises(RuntimeError):
            backend.write(PAYLOAD)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
