"""A04-S4: closing must report what was CONFIRMED, and the control path must not
queue behind data.

Two dishonest outcomes are prevented here:
  * "the native close call returned" is reported as "the child is gone" -- on
    Windows ConPTY can keep producing output while the pseudoconsole closes, and
    Microsoft documents that the native call's return behaviour changed around
    build 26100, so a returned call cannot be a confirmation;
  * a close request that has to wait for a full data queue before it can be seen
    (the X3 shape: nothing drains while nobody asks).

Everything below runs against the real backends with fake transports: no child
process, no ConPTY, no pty.

Run: python -B tests/test_a04_close_state.py [--repo PATH]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
REPO = args.repo.resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
try:
    from smartcli_core import PtySession
    from smartcli_core.pty_backend import PosixPtyBackend, WinptyBackend
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(REPO / "smartcli_core"):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)


class FakeProc:
    """A pywinpty-shaped process object whose liveness we control."""

    def __init__(self, dies: bool):
        self.dies = dies
        self.terminate_calls = 0

    def terminate(self, force=False):
        self.terminate_calls += 1
        return True

    def isalive(self):
        return not self.dies


class CloseProtocol(unittest.TestCase):
    def test_winpty_confirms_a_child_that_actually_died(self):
        backend = WinptyBackend()
        backend._proc = FakeProc(dies=True)
        backend.terminate()
        state = backend.close_state()
        self.assertTrue(state["close_requested"])
        self.assertTrue(state["closed_confirmed"])
        self.assertFalse(state["close_unconfirmed"])
        self.assertEqual(backend._proc, None)

    def test_winpty_reports_unconfirmed_for_a_child_that_survives(self):
        backend = WinptyBackend()
        backend._proc = FakeProc(dies=False)
        backend.terminate()
        state = backend.close_state()
        self.assertTrue(state["close_requested"])
        self.assertFalse(state["closed_confirmed"],
                         "a returned native call must never be reported as a confirmed exit")
        self.assertTrue(state["close_unconfirmed"])
        self.assertIn("still reported alive", state["last_progress"] or "")

    def test_posix_without_a_child_is_confirmed(self):
        backend = PosixPtyBackend()
        backend.terminate()
        state = backend.close_state()
        self.assertTrue(state["closed_confirmed"])
        self.assertFalse(state["close_unconfirmed"])

    def test_session_close_returns_the_state_and_never_upgrades_it(self):
        class UnconfirmedBackend:
            READ_BUDGET_CAPABLE = False

            def spawn(self, *a, **k):
                pass

            def read_nonblocking(self):
                return b""

            def read_status(self):
                return {}

            def write(self, data):
                pass

            def resize(self, *a):
                pass

            def is_alive(self):
                return True

            def terminate(self):
                pass

            def close_state(self):
                return {"close_requested": True, "closing": False, "closed_confirmed": False,
                        "close_unconfirmed": True, "output_eof": False,
                        "last_progress": "child still reported alive after terminate()"}

        sess = PtySession(backend=UnconfirmedBackend())
        state = sess.close()
        self.assertTrue(state["close_unconfirmed"])
        self.assertFalse(state["closed_confirmed"])
        self.assertEqual(state["basis_origin"], "runtime")
        self.assertTrue(sess.io_block()["close"]["close_unconfirmed"])
        self.assertTrue(sess.io_block()["close"]["close_requested"])

    def test_close_is_idempotent(self):
        backend = PosixPtyBackend()
        sess = PtySession(backend=backend)
        first = sess.close()
        second = sess.close()
        self.assertTrue(first["closed_confirmed"])
        self.assertTrue(second["closed_confirmed"])

    def test_control_state_does_not_travel_through_the_data_queue(self):
        # The close state lives in the backend/session, not as an item in the
        # byte queue: a full data buffer therefore cannot hide it. Asserted on the
        # real classes: close_state() must answer without consuming any data.
        backend = WinptyBackend()
        backend._queue.put(b"x" * 4096)          # a full buffer, nobody reading
        backend._proc = FakeProc(dies=True)
        state = backend.close_state()            # must not block or consume
        self.assertTrue(state["close_requested"] is False)
        self.assertEqual(backend._queue.qsize(), 1, "the data queue was untouched")
        backend.terminate()
        self.assertTrue(backend.close_state()["closed_confirmed"])
        self.assertEqual(backend._queue.qsize(), 1, "teardown does not drain the queue either")

    def test_daemon_close_reports_the_state(self):
        import importlib.util
        TUI = REPO / "skills" / "drive-tui" / "scripts" / "tui.py"
        spec = importlib.util.spec_from_file_location("drive_tui_close", TUI)
        tui = importlib.util.module_from_spec(spec)
        sys.modules["drive_tui_close"] = tui
        spec.loader.exec_module(tui)

        class Sess:
            def __init__(self):
                self.closed = 0

            def close(self):
                self.closed += 1
                return {"close_requested": True, "closing": False, "closed_confirmed": True,
                        "close_unconfirmed": False, "output_eof": True,
                        "last_progress": "reaped after SIGTERM", "generation": 1,
                        "basis_origin": "runtime"}

        sess = Sess()
        resp = tui._handle(sess, {"action": "close", "token": "token"}, "token")
        self.assertTrue(resp["_shutdown"])
        self.assertIn("close", resp)
        self.assertTrue(resp["close"]["closed_confirmed"])
        self.assertEqual(sess.closed, 1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
