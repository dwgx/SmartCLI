"""T04 regression: streaming SGR sub-parameters -- partition safety AND semantics.

Two independent oracles, because either one alone can be satisfied by a wrong
implementation:

* partition invariance -- the same byte stream fed whole, at every two-part cut,
  byte by byte, and in fixed-seed chunks must produce the same terminal state.
  Comparing against a whole-feed reference only proves self-consistency, so the
  *reference* is not trusted here for correctness -- the semantic tests below are.
* independent semantics -- ITU T.416 sub-parameters must land on the right
  attributes: 38:2::R:G:B is a truecolor foreground, 4:3 degrades to a plain
  underline and must NOT become italic (the naive ":" -> ";" rewrite produced
  ``4;3``, i.e. underline + italic), and the unsupported 58 underline-colour must
  not leak its operands into ordinary attributes (``58;2;;1;2;3`` means dim +
  bold + dim + italic to any parser that ignores 58).

Pure memory: no PTY, no process. Run: python tests/test_sgr_stream_regression.py
"""
from __future__ import annotations

import argparse
from pathlib import Path
import random
import sys
import unittest

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
sys.dont_write_bytecode = True
sys.path.insert(0, str(args.repo.resolve()))
try:
    from smartcli_core.screen_model import ScreenModel
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(
            (args.repo.resolve() / "smartcli_core")):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)


def state(model):
    """Everything a partition could plausibly change, not just the first row."""
    return (
        tuple(tuple(tuple(model.screen.buffer[y][x]) for x in range(model.cols))
              for y in range(model.rows)),
        model.cursor, model.cursor_hidden, model.title, model.alt_screen, model.app_cursor,
    )


def feed(chunks):
    model = ScreenModel(cols=30, rows=4)
    for chunk in chunks:
        model.feed(chunk)
    return model


class SgrStreamRegression(unittest.TestCase):
    def assert_partition_safe(self, payload: bytes) -> None:
        expected = state(feed([payload]))
        for cut in range(1, len(payload)):
            with self.subTest(cut=cut, payload=payload):
                self.assertEqual(state(feed([payload[:cut], payload[cut:]])), expected)
        self.assertEqual(state(feed([payload[i:i + 1] for i in range(len(payload))])), expected)
        for seed in range(4):
            rng = random.Random(seed)
            chunks, i = [], 0
            while i < len(payload):
                n = rng.randint(1, 7)
                chunks.append(payload[i:i + n])
                i += n
            self.assertEqual(state(feed(chunks)), expected)

    # -- partition invariance ------------------------------------------------
    def test_subparameter_vectors(self):
        for payload in [
            b"\x1b[4:3mX",
            b"\x1b[38:2::255:0:128mX",
            b"\x1b[48:2::0:255:0mX",
            b"\x1b[58:2::1:2:3mX",
            b"\x1b[38:5:196mX",
            b"\x1b[1;38:2::12:34:56m\xe4\xb8\xad\xe6\x96\x87\x1b[0m",
            b"\x1b[4:0mX",
            b"\x1b[38:2::255:0",
        ]:
            self.assert_partition_safe(payload)

    def test_controls(self):
        for payload in [
            b"\x1b[31mX", b"\x1b[2;5HX", "\x1b]0;标题\x07中文".encode(),
            b"\x1b[?1049hALT\x1b[?1049l", b"\x1b[?1h", b"\x1b7X", b"plain text",
        ]:
            self.assert_partition_safe(payload)

    def test_lookalikes_inside_strings_are_partition_safe(self):
        for payload in [b"\x1b]0;t\x1b[4:3mx\x07AFTER", b"\x1bPq\x1b[4:3m\x1b\\AFTER"]:
            self.assert_partition_safe(payload)

    # -- independent semantics ----------------------------------------------
    def test_truecolor_semantics(self):
        m = feed([b"\x1b[38:2::255:0:128mX"])
        self.assertEqual(m.screen.buffer[0][0].fg, "ff0080")
        self.assertEqual(m.display[0].rstrip(), "X")

    def test_truecolor_with_colour_space_slot(self):
        # 38:2:<cs>:R:G:B is the same colour with the slot filled in.
        m = feed([b"\x1b[38:2:0:255:0:128mX"])
        self.assertEqual(m.screen.buffer[0][0].fg, "ff0080")

    def test_truecolor_background(self):
        m = feed([b"\x1b[48:2::0:255:0mX"])
        self.assertEqual(m.screen.buffer[0][0].bg, "00ff00")

    def test_256_colour_semantics(self):
        m = feed([b"\x1b[38:5:196mX"])
        self.assertEqual(m.screen.buffer[0][0].fg, "ff0000")

    def test_curly_underline_degrades_without_italic(self):
        m = feed([b"\x1b[4:3mX"])
        self.assertTrue(m.screen.buffer[0][0].underscore)
        self.assertFalse(m.screen.buffer[0][0].italics)

    def test_every_underline_style_degrades_to_plain_underline(self):
        for sub in (b"1", b"2", b"4", b"5"):
            m = feed([b"\x1b[4:" + sub + b"mX"])
            self.assertTrue(m.screen.buffer[0][0].underscore, sub)
            self.assertFalse(m.screen.buffer[0][0].italics, sub)

    def test_underline_off(self):
        m = feed([b"\x1b[4mX\x1b[4:0mY"])
        self.assertTrue(m.screen.buffer[0][0].underscore)
        self.assertFalse(m.screen.buffer[0][1].underscore)

    def test_unsupported_underline_color_must_not_leak(self):
        m = feed([b"\x1b[31;58:2::1:2:3mX"])
        cell = m.screen.buffer[0][0]
        self.assertEqual(cell.fg, "red")
        self.assertFalse(cell.italics)
        self.assertFalse(cell.bold)
        self.assertEqual(m.display[0].rstrip(), "X")

    def test_unknown_subparameter_group_is_dropped_not_flattened(self):
        m = feed([b"\x1b[9:9mX"])
        cell = m.screen.buffer[0][0]
        self.assertFalse(cell.italics, "a dropped group must not become italic")
        self.assertFalse(cell.underscore)
        self.assertEqual(m.display[0].rstrip(), "X")

    def test_dropping_every_group_is_not_a_reset(self):
        # Emitting "ESC[m" would reset everything; the sequence must vanish.
        m = feed([b"\x1b[31mX\x1b[58:2::1:2:3mY"])
        self.assertEqual(m.screen.buffer[0][0].fg, "red")
        self.assertEqual(m.screen.buffer[0][1].fg, "red", "attributes must survive a dropped sequence")

    # -- bounded incomplete/oversized CSI ------------------------------------
    def test_incomplete_csi_is_held_not_drawn(self):
        m = feed([b"abc\x1b[4:"])
        self.assertEqual(m.display[0].rstrip(), "abc")

    def test_oversized_incomplete_csi_is_bounded_and_recovers(self):
        m = feed([b"\x1b[" + b"9" * 4000])
        self.assertEqual(m.display[0].rstrip(), "", "an abandoned sequence must not be drawn")
        self.assertLessEqual(len(m.stream._csi), m.stream._CSI_CAP)
        # The abandoned sequence still owns its final byte: the first byte in
        # the 0x40-0x7E final range ends it and is swallowed with it, so nothing
        # of the sequence reaches the grid. Recovery is what follows.
        m.feed(b"OK")                       # 'O' (0x4F) terminates the abandoned CSI
        self.assertEqual(m.display[0].rstrip(), "K")
        m.feed(b"\x1b[4:3mZ")
        self.assertEqual(m.display[0].rstrip(), "KZ")
        self.assertTrue(m.screen.buffer[0][1].underscore)
        self.assertFalse(m.screen.buffer[0][1].italics)

    def test_oversized_csi_that_finally_terminates(self):
        m = feed([b"\x1b[" + b"1" * 2000 + b"m", b"OK"])
        self.assertEqual(m.display[0].rstrip(), "OK")

    # -- chunking edge cases -------------------------------------------------
    def test_empty_chunk_and_eof(self):
        m = feed([b"abc\x1b[4"])
        self.assertEqual(m.display[0].rstrip(), "abc")
        m.feed(b"")                      # empty chunk: no-op, no flush
        self.assertEqual(m.display[0].rstrip(), "abc")
        m.feed(b":3mX")                  # the held sequence completes later
        self.assertEqual(m.display[0].rstrip(), "abcX")
        self.assertTrue(m.screen.buffer[0][3].underscore)
        self.assertFalse(m.screen.buffer[0][3].italics)

    def test_string_state_survives_chunk_boundaries(self):
        m = feed([b"\x1b]0;", b"ti", b"tle\x07", b"AFTER"])
        self.assertEqual(m.title, "title")
        self.assertEqual(m.display[0].rstrip(), "AFTER")

    def test_osc_lookalike_is_not_rewritten(self):
        m = feed([b"\x1b]0;t\x1b[4:3mx\x07AFTER"])
        self.assertEqual(m.title, "t\x1b[4:3mx", "the payload must keep its original bytes")
        self.assertEqual(m.display[0].rstrip(), "AFTER")

    def test_dcs_lookalike_is_not_rewritten(self):
        # pyte itself does not implement DCS (it draws the payload), so the claim
        # tested here is the narrow one the filter owns: the lookalike inside the
        # string must not be rewritten. A rewrite would have applied underline +
        # italic to everything after it.
        m = feed([b"\x1bPq\x1b[4:3m\x1b\\AFTER"])
        row = [m.screen.buffer[0][x] for x in range(m.cols)]
        self.assertFalse(any(c.underscore for c in row))
        self.assertFalse(any(c.italics for c in row))

    def test_string_terminated_by_st(self):
        m = feed([b"\x1b]0;a\x1b[4:3mb\x1b\\AFTER"])
        self.assertEqual(m.title, "a\x1b[4:3mb")
        self.assertEqual(m.display[0].rstrip(), "AFTER")

    def test_utf8_continuation_byte_is_not_a_c1_control(self):
        # U+4E1B is e4 b8 9b: a UTF-8 continuation byte that equals the C1 CSI
        # byte must never be treated as a control sequence introducer.
        m = feed(["丛 \x1b[4:3m中文\x1b[0m tail".encode("utf-8")])
        self.assertEqual(m.display[0].rstrip(), "丛 中文 tail")
        self.assertTrue(m.screen.buffer[0][3].underscore)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
