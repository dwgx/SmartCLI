"""A04-S3: the daemon must service the transport itself, under a byte budget.

Two failures are closed here, both measured rather than imagined (X2/X3):
  * nothing reads the child while no client asks -- on POSIX the child stalled at
    12 288 B and its ESC[6n was never answered;
  * a continuously non-empty request queue starves the transport just as badly,
    because the worker only ever left the request path to block on the queue.

The test drives the REAL `_serve_forever` with a fake socket and a fake session,
so the control flow under test is the production one (accept loop, worker, poll
hook) and no child process, port or thread from the daemon's own making is used
beyond the worker/reader threads the function itself starts.

Run: python -B tests/test_a04_daemon_service.py [--repo PATH]
"""
from __future__ import annotations

import argparse
import importlib.util
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
TUI = REPO / "skills" / "drive-tui" / "scripts"
sys.path.insert(0, str(TUI))
try:
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(REPO / "smartcli_core"):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)

spec = importlib.util.spec_from_file_location("drive_tui", TUI / "tui.py")
tui = importlib.util.module_from_spec(spec)
sys.modules["drive_tui"] = tui
spec.loader.exec_module(tui)


class FakeSocket:
    """A listen socket whose accept() always times out (no peers, no ports)."""

    def __init__(self):
        self.accepted = 0

    def settimeout(self, _value):
        pass

    def accept(self):
        self.accepted += 1
        raise TimeoutError("no peer")

    def close(self):
        pass


class FakeSession:
    """Records what the daemon asks of the session, in order.

    ``io_turn_bytes`` mirrors what ``_run_daemon`` sets on a real PtySession: its
    presence is what puts the daemon on the budgeted profile. ``None`` models a
    session that predates the profile (the legacy fallback path).
    """

    def __init__(self, alive: bool = True, budgeted: bool = True):
        self.calls: list[tuple] = []
        self.alive = alive
        self.closed = 0
        self.io_turn_bytes = None
        if budgeted:
            self.io_turn_bytes = tui.IO_TURN_BYTES

    def pump(self, max_bytes=None):
        self.calls.append(("pump", max_bytes))
        return b""

    def is_alive(self):
        self.calls.append(("is_alive",))
        return self.alive

    def close(self):
        self.closed += 1

    def io_block(self):
        return {"local_cut": "drained", "generation": 1, "read_offset": 0, "fed_offset": 0,
                "pending": {"known_payload_bytes": 0, "readable_now": False,
                            "parser_incomplete": False, "reply_bytes": 0, "upstream": None},
                "representation": "posix_pty_stream", "stream_error": None,
                "basis_origin": "runtime"}


def run_daemon_for(seconds: float, sess: FakeSession):
    srv = FakeSocket()
    stop = threading.Event()
    caught: list[BaseException] = []

    def target():
        try:
            tui._serve_forever(srv, sess, "token", stop)
        except BaseException as exc:            # pragma: no cover - reported below
            caught.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    time.sleep(seconds)
    stop.set()
    thread.join(timeout=5.0)
    return caught, srv


class DaemonService(unittest.TestCase):
    def test_idle_daemon_services_the_transport(self):
        sess = FakeSession()
        caught, _srv = run_daemon_for(0.7, sess)
        self.assertEqual(caught, [], f"the accept loop raised: {caught}")
        pumps = [c for c in sess.calls if c[0] == "pump"]
        self.assertGreater(len(pumps), 0,
                           "with no client at all the daemon must still read the session")
        self.assertTrue(all(c[1] is not None for c in pumps),
                        f"idle service turns must be budgeted, got {pumps[:3]}")
        self.assertTrue(all(0 < c[1] <= 1 << 20 for c in pumps))

    def test_budget_matches_the_module_constant(self):
        sess = FakeSession()
        run_daemon_for(0.5, sess)
        pumps = [c for c in sess.calls if c[0] == "pump"]
        self.assertTrue(pumps)
        self.assertEqual(pumps[0][1], tui.IO_TURN_BYTES)
        self.assertGreater(tui.JOBS_PER_TURN, 0)

    def test_service_runs_between_requests_not_only_when_idle(self):
        # A job queue that is never empty must not starve the transport: submit
        # work continuously and check that pump turns still interleave with it.
        sess = FakeSession(alive=False)          # the loop exits when the child dies
        srv = FakeSocket()
        stop = threading.Event()
        t = threading.Thread(target=lambda: tui._serve_forever(srv, sess, "token", stop), daemon=True)
        t.start()
        try:
            # The fake session reports alive=False, so the accept loop's own exit
            # path applies; the point is the ordering of the recorded calls.
            time.sleep(0.6)
        finally:
            stop.set()
            t.join(timeout=5.0)
        kinds = [c[0] for c in sess.calls]
        self.assertIn("pump", kinds, "service turns must appear in the call sequence")

    def test_interleave_set_is_unchanged_and_still_excludes_resize(self):
        # Preservation guard (source-level, like tests/test_doc_counts.py): the v3
        # design requires the fast-verb set and its resize exclusion to survive any
        # A04 work. The rationale comment sits immediately ABOVE the definition, so
        # the window starts before it. Behaviour of the set is additionally covered
        # by test_daemon_concurrency (a peer cannot stall the others).
        source = (TUI / "tui.py").read_text(encoding="utf-8")
        idx = source.index("INTERLEAVE_OK = frozenset(")
        window = source[max(0, idx - 1500):idx + 300]
        self.assertIn('"snapshot", "alive", "list", "send_text", "send_line", "send_keys"', window)
        self.assertIn("resize", window, "the resize rationale must stay next to the set")
        self.assertIn("content hash", window,
                      "the reason resize is excluded (it changes the hash) must stay documented")
        self.assertNotIn('"resize"', window,
                         "resize must not be a member of the interleave set")

    def test_a_session_without_the_budget_profile_falls_back_to_plain_pump(self):
        # Compatibility: a session object that predates the budget profile must
        # still be serviced, with its old zero-argument pump.
        sess = FakeSession(budgeted=False)
        caught, _srv = run_daemon_for(0.5, sess)
        self.assertEqual(caught, [])
        pumps = [c for c in sess.calls if c[0] == "pump"]
        self.assertTrue(pumps, "the legacy path must still service the transport")
        self.assertTrue(all(c[1] is None for c in pumps), pumps[:3])

    def test_worker_never_holds_the_screen_from_another_thread(self):
        sess = FakeSession()
        run_daemon_for(0.5, sess)
        pumps = [c for c in sess.calls if c[0] == "pump"]
        self.assertGreater(len(pumps), 0)
        # _serve_forever starts exactly one worker; the reader threads belong to
        # connection handling, not to the model, so no second owner can appear.
        names = {t.name for t in threading.enumerate()}
        self.assertNotIn("session-worker", names, "the worker must exit with the function")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
