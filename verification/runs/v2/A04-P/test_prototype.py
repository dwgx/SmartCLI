"""A04-P controls: every design invariant, plus the mutation that breaks it.

Each positive test states the invariant under the model; each paired negative
control removes exactly one mechanism and asserts the model now FAILS, so a
passing invariant is evidence the mechanism is load-bearing rather than
decoration. These are model-level results (E2-reference-model): no thread, no
socket, no PTY/ConPTY, no process is created.

Run: python -m unittest discover -s D:/Project/SmartCLI-v2-runs/A04-P -p "test_prototype.py" -v
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from prototype import (  # noqa: E402
    ByteQueue, Control, Daemon, FastJob, Observer, Owner, Reader, Screen, Transport, drive,
)


def build(*, mode="posix", cap=12, high=8, low=4, fragment=4, turn=8,
          fragments=(), replies=(), idle=True, interleave=True,
          resize_counts_as_action=False):
    transport = Transport(fragments, replies)
    queue = ByteQueue(cap, high, low)
    screen = Screen()
    reader = Reader(transport, queue, fragment=fragment, mode=mode)
    owner = Owner(queue, screen, turn_bytes=turn, fragment=fragment, reader=reader,
                  idle_service=idle)
    daemon = Daemon(owner, interleave=interleave,
                    resize_counts_as_action=resize_counts_as_action)
    control = Control()
    return {"transport": transport, "queue": queue, "screen": screen, "reader": reader,
            "owner": owner, "daemon": daemon, "control": control}


class BudgetInvariants(unittest.TestCase):
    def test_byte_budget_holds_and_delivery_is_exact_and_ordered(self):
        payload = bytes(range(40))
        s = build(fragments=[payload[i:i + 5] for i in range(0, len(payload), 5)])
        drive(s, ticks=40)
        q = s["queue"]
        self.assertLessEqual(q.max_pending, q.cap, "ingress never exceeds its byte cap")
        self.assertEqual(bytes(q.delivered), payload, "every accepted byte once, in order")
        self.assertLessEqual(s["owner"].max_turn, s["owner"].turn_bytes, "one turn is budgeted")
        self.assertLessEqual(s["transport"].max_read_size, 4, "read units are fragment-bounded")

    def test_reading_pauses_at_the_high_water_mark(self):
        s = build(fragments=[b"x" * 60], fragment=4)
        s["reader"].pump()
        self.assertEqual(len(s["queue"]), s["queue"].high,
                         "the reader stops at the high-water mark, below the hard cap")
        before = len(s["queue"])
        s["reader"].pump()
        self.assertEqual(len(s["queue"]), before, "a paused reader must not keep pulling")
        self.assertGreaterEqual(s["reader"].blocked_at_capacity, 1)
        self.assertGreaterEqual(s["reader"].waits, 1, "the pause is a wait, not a spin")

    def test_hard_cap_partial_acceptance_never_drops_the_tail(self):
        s = build(cap=12, high=12, low=4, fragments=[b"x" * 30], fragment=8)
        s["reader"].pump()                     # 8 accepted, then the partial 4 that fit
        self.assertEqual(len(s["queue"]), 12, "the pump stops exactly at the hard cap")
        self.assertGreaterEqual(s["reader"].blocked_at_capacity, 1, "capacity is a refusal")
        self.assertGreaterEqual(s["reader"].waits, 1, "the refusal waits for room")
        self.assertEqual(s["reader"].pump(), 0, "nothing is accepted while the queue is full")
        for _ in range(8):                     # owner drains, reader retries (the wake path)
            drive(s, ticks=1)
            s["reader"].pump()
        self.assertEqual(bytes(s["queue"].delivered), b"x" * 30,
                         "the whole finite stream is delivered once, in order: the tail refused "
                         "for capacity is re-offered, not dropped")
        self.assertLessEqual(s["queue"].max_pending, s["queue"].cap)

    def test_negative_control_uncapped_queue_breaks_the_byte_budget(self):
        # No byte cap and no watermark = the unbounded Windows queue the design
        # replaces: pending bytes grow with the producer instead of pausing it.
        payload = bytes(range(40))
        s = build(cap=10_000, high=10_000, low=10_000,
                  fragments=[payload[i:i + 5] for i in range(0, 40, 5)], turn=8)
        for _ in range(10):
            s["reader"].pump()
        q = s["queue"]
        self.assertGreater(q.max_pending, 12,
                           "without a real cap the pending byte count exceeds the design cap")
        self.assertEqual(s["reader"].waits, 0, "an unbounded queue never backpressures")

    def test_posix_idle_service_is_what_lets_a_finite_fixture_finish_unpolled(self):
        payload = b"READY> "
        s = build(mode="posix", fragments=[payload[i:i + 4] for i in range(0, len(payload), 4)])
        drive(s, ticks=8)                       # NO client polls, no request arrives
        self.assertEqual(bytes(s["screen"].text), payload,
                         "the owner's idle turn must consume the stream with nobody asking")

    def test_negative_control_without_idle_service_the_fixture_stalls(self):
        payload = b"READY> "
        s = build(mode="posix", idle=False, fragments=[payload[i:i + 4] for i in range(0, len(payload), 4)])
        drive(s, ticks=8)
        self.assertEqual(bytes(s["screen"].text), b"",
                         "no idle service => nothing is read until a client asks (the defect)")

    def test_device_replies_are_answered_without_a_client_request(self):
        s = build(mode="posix", fragments=[b"prompt", b"query"], replies=[b"\x1b[12;40R"])
        drive(s, ticks=6)
        self.assertEqual(s["reader"].replies_sent, 1, "CPR/DA answers must not wait for a client")

    def test_close_cannot_wait_forever_behind_full_data(self):
        s = build(cap=8, high=6, low=2, fragments=[b"x" * 40], fragment=8)
        s["reader"].pump()
        self.assertEqual(len(s["queue"]), 8, "queue saturated before the close arrives")
        s["control"].request_close(eof_via_data_queue=False)
        self.assertEqual(s["control"].control_ticks_waiting, 0)
        s["control"].finish()
        self.assertEqual(s["control"].state, "exited")

    def test_negative_control_eof_queued_behind_data_cannot_complete(self):
        s = build(cap=8, high=6, low=2, fragments=[b"x" * 40], fragment=8)
        s["reader"].pump()
        s["control"].request_close(eof_via_data_queue=True, queue=s["queue"])
        s["control"].finish()
        self.assertEqual(s["control"].state, "close_unconfirmed",
                         "an EOF sentinel inside a full data queue never arrives")


class InterleaveAndWatchers(unittest.TestCase):
    def test_fast_verbs_answered_during_a_long_wait(self):
        s = build(fragments=[b"a" * 4, b"b" * 4, b"NEEDLE "])
        job = FastJob("snapshot", tick=0)
        s["daemon"].submit(job)
        result = s["daemon"].action_wait(want_payload=b"NEEDLE", deadline=40, start_tick=0)
        self.assertEqual(result["satisfied_by"], "payload")
        self.assertIsNotNone(job.served_tick, "a fast verb must be answered inside the poll gap")

    def test_negative_control_without_interleave_the_fast_verb_is_starved(self):
        s = build(fragments=[b"a" * 4, b"b" * 4, b"NEEDLE "], interleave=False)
        job = FastJob("snapshot", tick=0)
        s["daemon"].submit(job)
        result = s["daemon"].action_wait(want_payload=b"NEEDLE", deadline=40, start_tick=0)
        self.assertEqual(result["satisfied_by"], "payload")
        self.assertIsNone(job.served_tick, "without the hook the request waits for the whole wait")

    def test_second_long_wait_still_queues_and_is_not_claimed_as_supported(self):
        s = build(fragments=[b"NEEDLE "])
        second = FastJob("wait_regex", tick=0)
        s["daemon"].submit(second)
        s["daemon"].action_wait(want_payload=b"NEEDLE", deadline=10, start_tick=0)
        self.assertIsNone(second.served_tick)
        self.assertIn(second, s["daemon"].deferred,
                      "a second long wait is deferred, not served as a fast verb")

    def test_resize_does_not_satisfy_an_action_specific_wait(self):
        s = build(fragments=[b"nothing yet"], resize_counts_as_action=False)
        s["daemon"].resize(during_action_wait=True)
        result = s["daemon"].action_wait(want_payload=b"NEVER", deadline=6, start_tick=0)
        self.assertIsNone(result["satisfied_by"],
                          "a geometry change must not be reported as the action landing")

    def test_negative_control_resize_counted_as_action_breaks_causality(self):
        s = build(fragments=[b"nothing yet"], resize_counts_as_action=True)
        s["daemon"].resize(during_action_wait=True)
        result = s["daemon"].action_wait(want_payload=b"NEVER", deadline=6, start_tick=0)
        self.assertEqual(result["satisfied_by"], "resize",
                         "the causality violation the exclusion rule prevents")

    def test_two_observers_share_one_committed_observation(self):
        s = build(fragments=[b"alpha ", b"beta"])
        a = Observer("a", lambda text: b"alpha" in text)
        b = Observer("b", lambda text: b"beta" in text)
        drive(s, ticks=6)
        a.evaluate(s["owner"], s["screen"])
        rev_a = a.last_revision
        b.evaluate(s["owner"], s["screen"])
        self.assertTrue(a.matched and b.matched)
        self.assertEqual(a.transport_reads + b.transport_reads, 0,
                         "read-only observers must not consume transport bytes")
        self.assertEqual(rev_a, b.last_revision, "both predicates judge the same committed revision")
        self.assertEqual(s["owner"].screen.owner_ident, "owner", "the screen has one writer")

    def test_negative_control_an_observer_reading_the_transport_is_detectable(self):
        s = build(fragments=[b"alpha ", b"beta"])
        a = Observer("a", lambda text: b"alpha" in text)
        drive(s, ticks=6)
        a.evaluate(s["owner"], s["screen"], read_transport=True)
        self.assertEqual(a.transport_reads, 1,
                         "the model can count a competing reader; the real daemon cannot")

    def test_observer_without_idle_service_sees_nothing(self):
        s = build(idle=False, fragments=[b"alpha "])
        a = Observer("a", lambda text: b"alpha" in text)
        drive(s, ticks=4)
        a.evaluate(s["owner"], s["screen"])
        self.assertFalse(a.matched, "no service turn => no committed observation to judge")


if __name__ == "__main__":
    unittest.main(verbosity=2)
