"""A04-S2: a budget-shaped observation must not be reported as a stable screen.

The defect this closes is not hypothetical in kind: a wait that says STABLE while
the runtime knows it has more bytes queued (or cannot tell) tells an agent "the
screen settled, act on it" at exactly the moment that is least true. The gate is
additive -- ``io_fn=None`` keeps the previous behaviour byte for byte, so every
existing caller is unaffected.

Pure memory, virtual time only where the waits allow it: the waits sleep in real
milliseconds, so every case is bounded to a few hundred ms. Run:
    python -B tests/test_a04_pending_readiness.py [--repo PATH]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
import unittest

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
sys.dont_write_bytecode = True
sys.path.insert(0, str(args.repo.resolve()))
try:
    from smartcli_core.readiness import (_io_blocks_stability, _io_epoch,
                                         wait_ready, wait_until_stable)
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(
            (args.repo.resolve() / "smartcli_core")):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)


def io_block(cut="drained", *, known=None, readable=None, parser=None, reply=0,
             fed=0, generation=1):
    return {"io": {"generation": generation, "read_offset": fed, "fed_offset": fed,
                   "pending": {"known_payload_bytes": known, "readable_now": readable,
                               "parser_incomplete": parser, "reply_bytes": reply,
                               "upstream": None},
                   "local_cut": cut, "representation": "posix_pty_stream",
                   "stream_error": None, "basis_origin": "runtime"}}["io"]


class IoGate(unittest.TestCase):
    def test_only_drained_is_complete(self):
        self.assertFalse(_io_blocks_stability(io_block("drained")))
        for cut in ("budget_limited", "unknown", "error"):
            self.assertTrue(_io_blocks_stability(io_block(cut)), cut)

    def test_pending_facts_block(self):
        self.assertTrue(_io_blocks_stability(io_block(known=5)))
        self.assertTrue(_io_blocks_stability(io_block(readable=True)))
        self.assertTrue(_io_blocks_stability(io_block(parser=True)))
        self.assertTrue(_io_blocks_stability(io_block(reply=17)))

    def test_absent_facts_never_block(self):
        # No io block at all (legacy caller) and all-null values must both pass:
        # blocking on "I do not know" would turn every wait into a timeout.
        self.assertFalse(_io_blocks_stability(None))
        self.assertFalse(_io_blocks_stability(io_block("drained", known=None,
                                                       readable=None, parser=None)))
        self.assertFalse(_io_blocks_stability(io_block(None, known=0, readable=False,
                                                       parser=False, reply=0)))

    def test_epoch_is_the_fed_offset(self):
        self.assertEqual(_io_epoch(io_block(fed=42)), 42)
        self.assertIsNone(_io_epoch(None))

    def test_budget_limited_screen_is_not_stable(self):
        # The screen is perfectly quiet and unchanged; only the runtime knows it
        # has more. Without the gate this returns True (that is the defect).
        state = {"cut": "budget_limited"}
        start = time.monotonic()
        settled = wait_until_stable(
            read_fn=lambda: b"", get_screen_hash_fn=lambda: 7,
            quiet_ms=30, poll_ms=5, max_wait_ms=180, grace_ms=0, io_fn=lambda: io_block(state["cut"]))
        self.assertFalse(settled, "a budget-limited observation must not be called stable")
        self.assertGreaterEqual(time.monotonic() - start, 0.03)

    def test_same_screen_settles_when_drained(self):
        settled = wait_until_stable(
            read_fn=lambda: b"", get_screen_hash_fn=lambda: 7,
            quiet_ms=30, poll_ms=5, max_wait_ms=400, grace_ms=0,
            io_fn=lambda: io_block("drained"))
        self.assertTrue(settled, "the gate must not block a genuinely drained screen")

    def test_legacy_callers_keep_the_old_behaviour(self):
        settled = wait_until_stable(
            read_fn=lambda: b"", get_screen_hash_fn=lambda: 7,
            quiet_ms=30, poll_ms=5, max_wait_ms=400, grace_ms=0)
        self.assertTrue(settled)

    def test_wait_ready_reports_timeout_while_budget_limited(self):
        # wait_ready must not upgrade a budget-shaped quiet screen to STABLE; the
        # marker path stays untouched, so a marker still wins immediately.
        reason, _snap = wait_ready(
            read_fn=lambda: b"", get_screen_hash_fn=lambda: 7,
            get_text_fn=lambda: "nothing here", get_snapshot_fn=lambda: {"text": "nothing here"},
            quiet_ms=20, poll_ms=5, max_wait_ms=150, grace_ms=0, min_wait_ms=0,
            io_fn=lambda: io_block("budget_limited"))
        self.assertEqual(reason, "TIMEOUT")

    def test_wait_ready_marker_still_wins(self):
        reason, _snap = wait_ready(
            read_fn=lambda: b"", get_screen_hash_fn=lambda: 7,
            get_text_fn=lambda: "READY>", get_snapshot_fn=lambda: {"text": "READY>"},
            marker="READY", quiet_ms=20, poll_ms=5, max_wait_ms=200, grace_ms=0,
            min_wait_ms=0, io_fn=lambda: io_block("budget_limited"))
        self.assertEqual(reason, "MARKER",
                         "a visible marker is an observation, not a completion claim: it stays ungated")

    def test_progress_from_a_poll_hook_invalidates_a_quiet_candidate(self):
        # The hook advances fed_offset without changing the screen hash, so a
        # quiet window measured before that progress must not be reused: the
        # wait settles only AFTER progress stops, i.e. later than quiet_ms alone.
        state = {"fed": 0}
        polls = {"n": 0}

        def hook():
            polls["n"] += 1
            if polls["n"] <= 3:        # the interleave path consumed bytes early on
                state["fed"] += 1

        start = time.monotonic()
        settled = wait_until_stable(
            read_fn=lambda: b"", get_screen_hash_fn=lambda: 7,
            quiet_ms=60, poll_ms=10, max_wait_ms=2000, grace_ms=0,
            on_poll=hook, io_fn=lambda: io_block("drained", fed=state["fed"]))
        elapsed = time.monotonic() - start
        self.assertTrue(settled, "a screen that stops progressing must still settle")
        self.assertGreater(polls["n"], 3, "the hook must have run repeatedly")
        self.assertGreaterEqual(elapsed, 0.06,
                                "the quiet window must restart after the last progress")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
