"""Tests of the injected reference models, not of SmartCLI or a native PTY."""
from __future__ import annotations
import errno
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.contracts import (InputProgress, IncompleteWrite, write_all_reference,
                              BudgetBuffer, accept_completion_claim)


class ProgressTests(unittest.TestCase):
    def test_accepted_has_no_ack(self):
        p = InputProgress("a", "g", 3)
        self.assertEqual((p.phase, p.app_ack), ("accepted", "unknown"))

    def test_partial_preserved_on_cancel(self):
        p = InputProgress("a", "g", 8).advance(3).stop("cancelled")
        self.assertEqual((p.written_bytes, p.write_state, p.outcome), (3, "partially_written", "cancelled"))
        with self.assertRaises(ValueError): p.advance(1)

    def test_empty_payload_is_written_not_verified(self):
        p = InputProgress("a", "g", 0)
        self.assertEqual(p.phase, "written")
        self.assertEqual(p.verification, "not_run")

    def test_written_is_not_an_application_ack(self):
        p = InputProgress("a", "g", 2).advance(2)
        self.assertEqual((p.phase, p.app_ack), ("written", "unknown"))

    def test_ack_must_match_generation_and_action(self):
        p = InputProgress("a", "g", 2).advance(2)
        for action, generation in [("b", "g"), ("a", "old")]:
            with self.assertRaises(ValueError): p.acknowledge(action, generation, "acknowledged")

    def test_ack_requires_complete_transport(self):
        with self.assertRaises(ValueError):
            InputProgress("a", "g", 2).advance(1).acknowledge("a", "g", "acknowledged")

    def test_independent_verification_does_not_invent_ack(self):
        p = InputProgress("a", "g", 1).advance(1).verify(True, "receipt-1")
        self.assertEqual((p.phase, p.app_ack), ("verified", "unknown"))
        self.assertEqual(p.verification_evidence_id, "receipt-1")

    def test_ignored_is_not_verified(self):
        p = InputProgress("a", "g", 1).advance(1).acknowledge("a", "g", "ignored")
        self.assertEqual((p.phase, p.verification), ("written", "not_run"))

    def test_late_cancel_does_not_erase_write(self):
        p = InputProgress("a", "g", 1).advance(1).stop("cancelled")
        self.assertEqual(p.write_state, "written")
        self.assertTrue(p.cancellation_too_late)

    def test_invalid_counts_and_identity(self):
        for args in [("", "g", 1), ("a", "", 1), ("a", "g", -1), ("a", "g", 1, 2)]:
            with self.assertRaises(ValueError): InputProgress(*args)
        with self.assertRaises(ValueError): InputProgress("a", "g", 1).advance(2)

    def test_verifier_needs_evidence(self):
        with self.assertRaises(ValueError): InputProgress("a", "g", 0).verify(True, "")


class WriteReferenceTests(unittest.TestCase):
    def test_short_writes_preserve_suffix(self):
        sent = []; sink = bytearray()
        def writer(data):
            sent.append(data); n = min(2, len(data)); sink.extend(data[:n]); return n
        p = write_all_reference(b"abcdef", writer, lambda _: None, lambda: 0, 1)
        self.assertEqual(bytes(sink), b"abcdef")
        self.assertEqual(sent, [b"abcdef", b"cdef", b"ef"])
        self.assertEqual(p.write_state, "written")

    def test_again_and_interrupt_do_not_repeat_prefix(self):
        seen = []; sink = bytearray(); actions = [2, "again", "intr", 99]; waits = []
        def writer(data):
            seen.append(data); act = actions.pop(0)
            if act == "again": raise BlockingIOError(errno.EAGAIN, "fixture")
            if act == "intr": raise InterruptedError(errno.EINTR, "fixture")
            n = min(act, len(data)); sink.extend(data[:n]); return n
        write_all_reference("中AB".encode(), writer, waits.append, lambda: 0, 1)
        self.assertEqual(bytes(sink), "中AB".encode())
        self.assertEqual(seen[1], seen[2]); self.assertEqual(seen[2], seen[3])
        self.assertEqual(len(waits), 1)

    def test_zero_progress_reaches_deadline(self):
        now = [0.0]
        def wait(_): now[0] += 0.6
        with self.assertRaises(IncompleteWrite) as cm:
            write_all_reference(b"x", lambda _: 0, wait, lambda: now[0], 1)
        self.assertEqual((cm.exception.progress.written_bytes, cm.exception.progress.outcome), (0, "timeout"))

    def test_cancel_after_partial(self):
        n = [0]
        def write(_): n[0] += 1; return 1
        with self.assertRaises(IncompleteWrite) as cm:
            write_all_reference(b"abc", write, lambda _: None, lambda: 0, 1, lambda: n[0] == 1)
        self.assertEqual((cm.exception.progress.written_bytes, cm.exception.progress.outcome), (1, "cancelled"))

    def test_error_after_partial(self):
        calls = [0]
        def write(_):
            calls[0] += 1
            if calls[0] > 1: raise OSError(errno.EPIPE, "fixture")
            return 1
        with self.assertRaises(IncompleteWrite) as cm:
            write_all_reference(b"abc", write, lambda _: None, lambda: 0, 1)
        self.assertEqual(cm.exception.progress.written_bytes, 1)

    def test_invalid_backend_return(self):
        for result in [True, -1, "2", 100]:
            with self.subTest(result=result), self.assertRaises(IncompleteWrite):
                write_all_reference(b"a", lambda _: result, lambda _: None, lambda: 0, 1)

    def test_writable_wait_failure_keeps_partial_progress(self):
        calls = [0]
        def write(_):
            calls[0] += 1
            if calls[0] > 1: raise BlockingIOError(errno.EAGAIN, "fixture")
            return 1
        def wait(_): raise OSError(errno.EBADF, "fixture")
        with self.assertRaises(IncompleteWrite) as cm:
            write_all_reference(b"abc", write, wait, lambda: 0, 1)
        self.assertEqual((cm.exception.progress.written_bytes, cm.exception.progress.outcome), (1, "failed"))

    def test_empty_payload_makes_no_call(self):
        def write(_): self.fail("empty payload must not write")
        p = write_all_reference(b"", write, lambda _: None, lambda: 0, 1)
        self.assertEqual(p.write_state, "written")

    def test_interrupt_flood_is_bounded(self):
        def write(_): raise InterruptedError(errno.EINTR, "fixture")
        with self.assertRaises(IncompleteWrite) as cm:
            write_all_reference(b"x", write, lambda _: None, lambda: 0, 1, max_attempts=3)
        self.assertEqual(cm.exception.progress.outcome, "failed")


class BufferTests(unittest.TestCase):
    def test_full_is_backpressure_not_drop(self):
        q = BudgetBuffer(6, 3)
        self.assertTrue(q.offer(b"abc")); self.assertTrue(q.offer(b"def"))
        self.assertFalse(q.offer(b"ghi"))
        self.assertEqual((q.pending_bytes, q.max_seen), (6, 6))
        self.assertEqual(q.consume(6), b"abcdef")
        self.assertTrue(q.offer(b"ghi")); self.assertEqual(q.consume(6), b"ghi")

    def test_partial_consume_retains_suffix(self):
        q = BudgetBuffer(6, 3); q.offer(b"abc"); q.offer(b"def")
        self.assertEqual(q.consume(2), b"ab")
        self.assertEqual(q.pending_bytes, 4)
        self.assertEqual(q.consume(3), b"cde")
        self.assertEqual(q.consume(3), b"f")

    def test_eof_not_blocked_by_full_data(self):
        q = BudgetBuffer(3, 3); q.offer(b"abc"); q.signal_eof()
        self.assertTrue(q.eof); self.assertFalse(q.drained)
        self.assertEqual(q.consume(3), b"abc"); self.assertTrue(q.drained)
        with self.assertRaises(RuntimeError): q.offer(b"x")

    def test_close_request_keeps_final_output_readable(self):
        q = BudgetBuffer(3, 3); q.offer(b"abc"); q.begin_close()
        self.assertEqual(q.consume(3), b"abc"); self.assertFalse(q.drained)
        self.assertTrue(q.offer(b"end")); q.signal_eof()
        self.assertEqual(q.consume(3), b"end"); self.assertTrue(q.drained)
        with self.assertRaises(RuntimeError): q.offer(b"x")

    def test_close_request_is_not_eof_or_exit(self):
        q = BudgetBuffer(3, 3); q.begin_close()
        self.assertTrue(q.closing); self.assertFalse(q.eof); self.assertFalse(q.drained)

    def test_fragment_and_budget_validation(self):
        for capacity, fragment in [(0, 1), (2, 3), (2, 0)]:
            with self.assertRaises(ValueError): BudgetBuffer(capacity, fragment)
        q = BudgetBuffer(4, 2)
        for value in [b"", b"123", "ab"]:
            with self.assertRaises(ValueError): q.offer(value)
        with self.assertRaises(ValueError): q.consume(0)

    def test_unicode_bytes_preserved_across_fragments(self):
        data = "A中文🚀".encode(); q = BudgetBuffer(6, 3); got = bytearray()
        for i in range(0, len(data), 3):
            part = data[i:i+3]
            if not q.offer(part):
                got.extend(q.consume(4)); self.assertTrue(q.offer(part))
        q.signal_eof()
        while not q.drained: got.extend(q.consume(2))
        self.assertEqual(bytes(got), data)
        self.assertLessEqual(q.max_seen, 6)


class ClaimTests(unittest.TestCase):
    def test_quiet_never_proves_command_finished(self):
        self.assertFalse(accept_completion_claim("quiet", "command_finished", "q1"))

    def test_exit_requires_evidence(self):
        self.assertFalse(accept_completion_claim("process_exit", "command_finished"))
        self.assertTrue(accept_completion_claim("process_exit", "command_finished", "exit1"))

    def test_marker_only_proves_state(self):
        self.assertTrue(accept_completion_claim("rendered_text_regex", "state_matches"))
        self.assertFalse(accept_completion_claim("rendered_text_regex", "verified", "m1"))

    def test_independent_verification(self):
        self.assertTrue(accept_completion_claim("independent_verifier", "verified", "file1"))
        self.assertFalse(accept_completion_claim("unrecognized", "verified", "x"))

if __name__ == "__main__": unittest.main()
