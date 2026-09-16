"""A04-S1: byte-budgeted transport, and the accounting that goes with it.

The budget exists because a single "read whatever is there" call is what lets an
idle daemon discover 271 KB of unparsed output at its first client contact (X2)
and what lets a request-triggered pump swallow a whole backlog at once. This
slice does NOT enable that budget anywhere in the daemon (S3 does): it adds the
capability, the cut vocabulary and the compatibility rules, and proves them
against fake transports.

Rules under test, in the v3 design's wording:
  * a single/one-turn budget cannot be exceeded by a perpetually readable source;
  * many bounded turns concatenate to exactly the delivered stream (no loss, no
    duplication), including when a read stops in the middle of a chunk;
  * a turn that consumes exactly its budget is NOT reported as drained;
  * a legacy backend that only implements the original ABC still works through
    the default (unbudgeted) path;
  * a backend whose read raises TypeError internally must not be retried/probed
    and must not have its error masked;
  * the capability is passive: nothing turns it on unless a caller passes a
    budget.

Pure memory: no PTY, no child process, no thread. Run:
    python -B tests/test_a04_read_budget.py [--repo PATH]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
sys.dont_write_bytecode = True
sys.path.insert(0, str(args.repo.resolve()))
try:
    from smartcli_core import PtySession
    from smartcli_core.pty_backend import (
        PtyBackend, ReadBudgetUnsupported, supports_read_budget,
    )
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(
            (args.repo.resolve() / "smartcli_core")):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)


STREAM = b"alpha|beta|gamma|delta|epsilon|zeta|eta|theta"


class LegacyBackend(PtyBackend):
    """Implements the ORIGINAL abstract interface only -- no budget capability."""

    READ_BUDGET_CAPABLE = False   # explicit, like a third-party backend that opts out

    def __init__(self, data: bytes):
        self._data = bytearray(data)
        self.read_calls = 0

    def spawn(self, cmd, cols, rows):  # pragma: no cover - not used here
        raise NotImplementedError

    def read_nonblocking(self) -> bytes:
        self.read_calls += 1
        out = bytes(self._data)
        self._data.clear()
        return out

    def write(self, data: bytes) -> None:  # pragma: no cover
        pass

    def resize(self, cols, rows):  # pragma: no cover
        pass

    def is_alive(self) -> bool:  # pragma: no cover
        return True

    def terminate(self) -> None:  # pragma: no cover
        pass


class BudgetBackend(LegacyBackend):
    """A transport that hands out at most ``quantum`` bytes per budgeted read."""

    READ_BUDGET_CAPABLE = True

    def __init__(self, data: bytes, quantum: int | None = None):
        super().__init__(data)
        self.quantum = quantum
        self.budgeted_calls = 0

    def _read_budgeted(self, max_bytes: int) -> bytes:
        self.budgeted_calls += 1
        limit = max_bytes if self.quantum is None else min(max_bytes, self.quantum)
        out = bytes(self._data[:limit])
        del self._data[:limit]
        return out

    def read_status(self) -> dict:
        return {"readable_now": bool(self._data), "eof": False, "error": None,
                "queued_payload_bytes": len(self._data), "reader_held_payload_bytes": 0,
                "generation": 1}


class ExplodingBackend(BudgetBackend):
    """Raises TypeError from inside its own read (a real backend bug, not a signature
    mismatch) -- the session must not treat that as 'wrong signature, read again'."""

    def _read_budgeted(self, max_bytes: int) -> bytes:
        self.budgeted_calls += 1
        raise TypeError("internal backend bug: expected str, got NoneType")


class ReadBudgetS1(unittest.TestCase):
    def test_capability_is_declared_not_probed(self):
        self.assertTrue(supports_read_budget(BudgetBackend(b"")))
        self.assertFalse(supports_read_budget(LegacyBackend(b"")))
        self.assertTrue(supports_read_budget.__doc__)

    def test_budget_is_never_exceeded_by_a_perpetually_readable_source(self):
        backend = BudgetBackend(STREAM)
        sess = PtySession(backend=backend)
        got = bytearray()
        reads = []
        for _ in range(len(STREAM) + 4):
            chunk = sess.pump(max_bytes=4)
            reads.append(len(chunk))
            got += chunk
        self.assertEqual(bytes(got), STREAM)
        self.assertTrue(all(n <= 4 for n in reads), f"a turn exceeded its budget: {reads}")
        self.assertEqual(sess.io_state()["io"]["pending"]["known_payload_bytes"], 0)

    def test_many_bounded_turns_concatenate_without_loss_or_duplication(self):
        for quantum in (1, 2, 3, 5, 7, 64):
            backend = BudgetBackend(STREAM, quantum=quantum)
            sess = PtySession(backend=backend)
            out = bytearray()
            for _ in range(64):
                out += sess.pump(max_bytes=3)
                if not backend._data:
                    break
            with self.subTest(quantum=quantum):
                self.assertEqual(bytes(out), STREAM, "delivered stream must be preserved exactly")

    def test_offsets_advance_in_one_generation(self):
        sess = PtySession(backend=BudgetBackend(STREAM, quantum=4))
        sess.pump(max_bytes=4)
        sess.pump(max_bytes=4)
        io = sess.io_state()["io"]
        self.assertEqual(io["read_offset"], 8)
        self.assertEqual(io["fed_offset"], 8)
        self.assertLessEqual(io["fed_offset"], io["read_offset"])
        self.assertEqual(io["basis_origin"], "runtime")
        self.assertEqual(io["local_cut"], "budget_limited")

    def test_exactly_spent_budget_is_not_reported_as_drained(self):
        # 8 bytes of data, budget 8: the turn is full, so nothing may claim the
        # stream is finished even though the next check would find nothing.
        sess = PtySession(backend=BudgetBackend(b"12345678"))
        sess.pump(max_bytes=8)
        self.assertEqual(sess.io_state()["io"]["local_cut"], "budget_limited")

    def test_a_short_turn_can_report_drained(self):
        sess = PtySession(backend=BudgetBackend(b"12"))
        sess.pump(max_bytes=8)
        self.assertEqual(sess.io_state()["io"]["local_cut"], "drained")

    def test_unknown_is_null_not_zero(self):
        legacy = PtySession(backend=LegacyBackend(b""))
        pending = legacy.io_state()["io"]["pending"]
        self.assertIsNone(pending["known_payload_bytes"],
                          "a transport that cannot count must report null, not 0")
        self.assertIsNone(pending["readable_now"])

    def test_legacy_zero_arg_backend_still_works_through_the_default_path(self):
        backend = LegacyBackend(STREAM)
        sess = PtySession(backend=backend)
        data = sess.pump()                       # no budget: the old code path
        self.assertEqual(data, STREAM)
        self.assertEqual(backend.read_calls, 1)
        self.assertFalse(hasattr(backend, "_read_budgeted"))

    def test_requesting_a_budget_from_a_legacy_backend_refuses_before_readin(self):
        backend = LegacyBackend(STREAM)
        sess = PtySession(backend=backend)
        with self.assertRaises(ReadBudgetUnsupported):
            sess.pump(max_bytes=4)
        self.assertEqual(backend.read_calls, 0,
                         "refusal must happen before any read, not after draining it")

    def test_internal_type_error_is_not_masked_by_a_retry(self):
        backend = ExplodingBackend(STREAM)
        sess = PtySession(backend=backend)
        with self.assertRaises(TypeError):
            sess.pump(max_bytes=4)
        self.assertEqual(backend.budgeted_calls, 1,
                         "an internal TypeError must propagate once, not be probed twice")

    def test_capability_is_passive_without_a_caller_budget(self):
        backend = BudgetBackend(STREAM)
        sess = PtySession(backend=backend)
        sess.pump()                              # default path
        self.assertEqual(backend.budgeted_calls, 0,
                         "nothing may switch the session into the budget profile by itself")

    def test_default_pump_signature_is_unchanged(self):
        import inspect
        sig = inspect.signature(PtySession.pump)
        params = list(sig.parameters)
        self.assertEqual(params[:2], ["self", "max_bytes"])
        self.assertIsNone(sig.parameters["max_bytes"].default,
                          "the new parameter must default to the previous behaviour")

    def test_reply_bytes_are_reported_and_cleared(self):
        # A device query produces a reply; with a healthy transport it is written
        # and the pending counter returns to zero.
        class ReplyingBackend(BudgetBackend):
            def __init__(self):
                super().__init__(b"\x1b[6n")
                self.written = bytearray()

            def write(self, data: bytes) -> None:
                self.written += data

        backend = ReplyingBackend()
        sess = PtySession(backend=backend)
        sess.pump(max_bytes=16)
        self.assertGreater(len(backend.written), 0, "a CPR query must still be answered")
        self.assertEqual(sess.io_state()["io"]["pending"]["reply_bytes"], 0)

    # -- the production backends, not just a test double ---------------------
    def test_winpty_budgeted_read_never_exceeds_its_budget(self):
        # No ConPTY here: the queue is filled directly, which is exactly what the
        # reader thread would do. This is the production method under test.
        from smartcli_core.pty_backend import WinptyBackend
        backend = WinptyBackend()
        backend._queue.put(STREAM)                     # one chunk, larger than the budget
        chunks = []
        while True:
            chunk = backend._read_budgeted(4)
            if not chunk:
                break
            chunks.append(chunk)
        delivered = b"".join(chunks)
        self.assertEqual(delivered, STREAM, "splitting a big chunk must preserve the stream")
        self.assertTrue(all(len(c) <= 4 for c in chunks), [len(c) for c in chunks])

    def test_winpty_carry_is_accounted_not_hidden(self):
        from smartcli_core.pty_backend import WinptyBackend
        backend = WinptyBackend()
        backend._queue.put(STREAM)
        self.assertEqual(backend._read_budgeted(4), STREAM[:4])
        status = backend.read_status()
        self.assertEqual(status["reader_held_payload_bytes"], len(STREAM) - 4)
        self.assertEqual(status["queued_payload_bytes"], 0)
        rest = backend._read_budgeted(len(STREAM))
        self.assertEqual(rest, STREAM[4:])
        self.assertEqual(backend.read_status()["reader_held_payload_bytes"], 0)

    def test_winpty_eof_sentinel_is_latched_and_never_returned(self):
        from smartcli_core.pty_backend import WinptyBackend
        backend = WinptyBackend()
        backend._queue.put(b"tail")
        backend._queue.put(None)
        self.assertEqual(backend._read_budgeted(64), b"tail")
        self.assertTrue(backend.read_status()["eof"])
        self.assertEqual(backend._read_budgeted(64), b"",
                         "the sentinel is not data and must not reappear")

    def test_posix_budgeted_read_respects_budget_and_status(self):
        # Real production method with an injected transport (no pty on Windows).
        import os
        import select as select_mod
        from unittest.mock import patch
        from smartcli_core.pty_backend import PosixPtyBackend

        backend = PosixPtyBackend()
        backend._fd = 987654
        source = bytearray(STREAM)
        record = {"select_calls": 0, "read_sizes": []}

        def fake_select(reads, writes, errors, timeout=None):
            record["select_calls"] += 1
            return ([backend._fd] if source else []), [], []

        def fake_read(fd, size):
            record["read_sizes"].append(size)
            out = bytes(source[:size])
            del source[:size]
            return out

        try:
            with patch.object(os, "read", fake_read), patch.object(select_mod, "select", fake_select):
                chunks = [backend._read_budgeted(4) for _ in range(len(STREAM))]
        finally:
            backend._fd = None
        self.assertEqual(b"".join(chunks), STREAM)
        self.assertTrue(all(len(c) <= 4 for c in chunks))
        self.assertTrue(all(s <= 4 for s in record["read_sizes"]),
                        f"os.read was asked for more than the budget: {record['read_sizes']}")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
