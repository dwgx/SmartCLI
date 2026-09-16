"""A04-S2p: the runtime must be able to say "I am mid-sequence", not guess.

A caller that reads the screen while a CSI or a multi-byte UTF-8 character is
half-delivered is looking at a state that is not yet the program's state. Before
this diagnostic the runtime had no way to say so, and the only available answers
were "looks fine" and "raise". The rule under test is the strict one from the v3
design: a half-CSI or half-UTF-8 must be ``True``, a clean boundary ``False``, and
an uninspectable decoder ``None`` -- never a confident ``False``.

Read-only: nothing here changes parsing behaviour (T04's tests still pass).
Run: python -B tests/test_a04_parser_pending.py [--repo PATH]
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
    from smartcli_core import PtySession, ScreenModel
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(
            (args.repo.resolve() / "smartcli_core")):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)


class ParserPending(unittest.TestCase):
    def model(self) -> ScreenModel:
        return ScreenModel(cols=40, rows=4)

    def test_clean_screen_reports_complete(self):
        m = self.model()
        m.feed(b"plain text\n")
        self.assertIs(m.stream_incomplete(), False)

    def test_half_csi_is_incomplete(self):
        m = self.model()
        m.feed(b"ok\x1b[38:2")               # held back by the streaming filter
        self.assertIs(m.stream_incomplete(), True)

    def test_half_utf8_is_incomplete(self):
        m = self.model()
        m.feed("中".encode("utf-8")[:2])      # a split 3-byte character
        self.assertIs(m.stream_incomplete(), True,
                      "pyte's incremental decoder is holding the prefix")

    def test_open_string_is_incomplete(self):
        m = self.model()
        m.feed(b"\x1b]0;a title without a terminator")
        self.assertIs(m.stream_incomplete(), True)

    def test_completing_the_sequence_clears_it(self):
        m = self.model()
        m.feed(b"ok\x1b[38:2")
        self.assertIs(m.stream_incomplete(), True)
        m.feed(b"::255:0:0mX")
        self.assertIs(m.stream_incomplete(), False)

    def test_split_utf8_clears_after_the_rest_arrives(self):
        m = self.model()
        whole = "中文".encode("utf-8")
        m.feed(whole[:2])
        self.assertIs(m.stream_incomplete(), True)
        m.feed(whole[2:])
        self.assertIs(m.stream_incomplete(), False)
        self.assertIn("中", m.text())

    def test_uninspectable_decoder_is_unknown_not_false(self):
        m = self.model()
        real = m.stream.utf8_decoder
        try:
            del m.stream.utf8_decoder            # simulate a pyte without the hook
            self.assertIsNone(m.stream_incomplete(),
                              "a missing decoder must be unknown, never a confident False")
        finally:
            m.stream.utf8_decoder = real

    def test_session_surfaces_the_same_truth(self):
        class NullBackend:
            READ_BUDGET_CAPABLE = True

            def read_nonblocking(self):
                return b""

            def _read_budgeted(self, max_bytes):
                return b""

            def read_status(self):
                return {"readable_now": False, "eof": False, "error": None,
                        "queued_payload_bytes": 0, "reader_held_payload_bytes": 0,
                        "generation": 1}

            def spawn(self, *a, **k):
                pass

            def write(self, data):
                pass

            def resize(self, *a):
                pass

            def is_alive(self):
                return True

            def terminate(self):
                pass

        sess = PtySession(backend=NullBackend())
        sess.model.feed(b"\x1b[4:")
        self.assertIs(sess.io_block()["pending"]["parser_incomplete"], True)
        sess.model.feed(b"3mX")
        self.assertIs(sess.io_block()["pending"]["parser_incomplete"], False)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
