#!/usr/bin/env python3
"""Graphics escape sequences must never reach the cell grid.

A program that draws an image in the terminal (yazi, chafa, timg, viu, or this
repo's own ``python -m ui sixel``) emits a graphics escape sequence: a DCS for
sixel, an APC for the kitty protocol, and SOS/PM/APC alongside them for tmux
passthrough and other control strings. Those payloads are base64 or raster
data, thousands of bytes of it.

``pyte`` has branches for CSI and OSC but none for DCS/SOS/PM/APC: the
parser falls through to ``draw()``, so the payload used to be drawn as literal
text -- an agent driving an image previewing program read

    A\x1b_Gf=100;a=T;QUFBQQ==\x1b\\B   ->  'AGf=100;a=T;QUFBQQ==B'
    A\x1bPq#0;2;100;0;0#1~~~\x1b\\B   ->  'Aq#0;2;100;0;0#1~~~B'

and, worse, could not have noticed from any diagnostic: ``feed_errors`` stayed
0 for both, because pyte parsed them "successfully". A real terminal shows
nothing for a string it does not interpret; that is what this locks.

The counterweight is OSC, which carries meaning pyte does consume (window
title, hyperlink). It must keep being forwarded -- so every "dropped" claim
here is paired with a guard that OSC still works.

Oracles, not self-consistency:
  * partition invariance -- the same stream fed whole, at every two-part cut,
    byte by byte, and in fixed-seed chunks must reach one identical terminal
    state. A PTY read boundary lands inside these sequences constantly, so a
    filter that only works when the whole sequence arrives at once is wrong.
  * the grid -- what an agent actually reads. Never a counter.

Pure memory: no PTY, no process.
Run: python -B tests/test_graphics_payload.py
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

ST = b"\x1b\\"

#: kitty graphics: direct PNG data, base64 ("QUFBQQ==" is "AAA").
KITTY_SEQ = b"\x1b_Gf=100;a=T;QUFBQQ==" + ST
#: sixel (VT330/340): raster attrs, a colour register, a band of sixel data.
SIXEL_SEQ = b"\x1bPq#0;2;100;0;0#1~~~" + ST
#: sixel with a run-length repeat, a graphics-newline and a raw backslash.
#: 0x5C is a legal sixel DATA character (char = 0x3F + mask, so 0x3F..0x7E),
#: which is why a bare '\' must not be treated as a terminator: doing so would
#: cut this image short and spill its remainder onto the grid as text.
SIXEL_BSLASH_SEQ = b"\x1bPq#0;2;100;0;0#1!5\\-~~~$" + ST
#: OSC 1337 (iTerm2 inline image): an image payload that arrives as an OSC and
#: was already clean. Locked here so "fix" cannot quietly become "drop OSC".
OSC_1337_SEQ = b"\x1b]1337;File=name=x.png:QUFBQQ==" + ST

#: The two reproducers, with text on both sides of the sequence so the
#: assertion proves the neighbours survived, not just that the payload went.
KITTY = b"A" + KITTY_SEQ + b"B"
SIXEL = b"A" + SIXEL_SEQ + b"B"
SIXEL_BSLASH = b"A" + SIXEL_BSLASH_SEQ + b"B"
OSC_1337 = b"A" + OSC_1337_SEQ + b"B"


def feed(chunks, cols: int = 60, rows: int = 4) -> ScreenModel:
    model = ScreenModel(cols=cols, rows=rows)
    for chunk in chunks:
        model.feed(chunk)
    return model


def state(model: ScreenModel):
    """Everything a partition could plausibly change, not just the first row."""
    return (
        tuple(tuple(tuple(model.screen.buffer[y][x]) for x in range(model.cols))
              for y in range(model.rows)),
        model.cursor, model.cursor_hidden, model.title, model.alt_screen,
        model.app_cursor,
    )


def row0(model: ScreenModel) -> str:
    return model.display[0].rstrip()


class GraphicsPayloadTest(unittest.TestCase):
    def assert_partition_safe(self, payload: bytes) -> None:
        """Every way of cutting the stream must reach one identical state."""
        expected = state(feed([payload]))
        for cut in range(1, len(payload)):
            self.assertEqual(state(feed([payload[:cut], payload[cut:]])), expected,
                             f"two-part split at byte {cut} diverged")
        one_at_a_time = [payload[i:i + 1] for i in range(len(payload))]
        self.assertEqual(state(feed(one_at_a_time)), expected,
                         "byte-at-a-time feed diverged")
        rnd = random.Random(20261001)
        for _ in range(40):
            cuts = sorted(rnd.sample(range(1, len(payload)),
                                     min(6, len(payload) - 1)))
            chunks = [payload[a:b] for a, b in zip([0] + cuts, cuts + [None])]
            self.assertEqual(state(feed(chunks)), expected,
                             f"random chunking {cuts} diverged")

    # -- the two reproducers ------------------------------------------------
    def test_kitty_apc_payload_is_not_on_the_grid(self):
        m = feed([KITTY])
        self.assertEqual(row0(m), "AB",
                         "kitty base64 payload drawn as text again")
        self.assertNotIn("QUFBQQ", m.display[0])

    def test_sixel_dcs_payload_is_not_on_the_grid(self):
        m = feed([SIXEL])
        self.assertEqual(row0(m), "AB",
                         "sixel payload drawn as text again")
        self.assertNotIn("#1~~~", m.display[0])

    def test_all_four_control_string_introducers_are_swallowed(self):
        # DCS 'P' (sixel, DECRQSS), SOS 'X', PM '^' (xterm), APC '_' (kitty).
        # The payload is arbitrary binary on purpose -- a CAN byte and a byte
        # that is not valid UTF-8 -- because that is what a graphics string
        # actually carries.
        payload = b"payload~#0;2;100;0;0\x18\xff"
        for name, intro in (("DCS", b"P"), ("SOS", b"X"), ("PM", b"^"), ("APC", b"_")):
            with self.subTest(name):
                m = feed([b"A" + b"\x1b" + intro + payload + ST + b"B"])
                self.assertEqual(row0(m), "AB",
                                 f"{name} payload reached the grid")

    def test_a_counter_would_not_have_caught_this(self):
        # The reason the defect survived: pyte parsed a graphics string
        # "successfully", so feed_errors stayed 0 while the grid was corrupt.
        # Asserting on the counter would have been green on the broken build;
        # the grid is the only oracle, and it is what the cases above use.
        for payload in (KITTY, SIXEL, OSC_1337):
            with self.subTest(payload[:3]):
                self.assertEqual(row0(feed([payload])), "AB")

    # -- chunk boundaries ---------------------------------------------------
    def test_every_split_point_is_safe(self):
        for payload in (KITTY, SIXEL, SIXEL_BSLASH, OSC_1337):
            with self.subTest(payload[:3]):
                self.assert_partition_safe(payload)

    def test_split_between_esc_and_st_final_byte(self):
        # The terminator's ESC lands at the end of one read and its '\' at the
        # start of the next -- the shape a chunked PTY read really produces.
        for intro, name in ((b"P", "DCS"), (b"_", "APC")):
            with self.subTest(name):
                m = feed([b"A" + b"\x1b" + intro + b"payload#1~~~",
                          b"\x1b", b"\\B"])
                self.assertEqual(row0(m), "AB")

    def test_string_still_open_is_not_a_complete_observation(self):
        m = feed([b"A\x1b_Gf=100;a=T;QUFBQQ=="])          # no ST yet
        self.assertEqual(row0(m), "A")
        self.assertTrue(m.stream_incomplete(),
                        "an unterminated control string must not read as "
                        "a clean boundary")
        m.feed(ST + b"B")                                   # the rest arrives
        self.assertEqual(row0(m), "AB")

    def test_esc_inside_a_payload_does_not_restart_the_filter(self):
        # A lookalike CSI in the payload is payload: not rewritten, not drawn,
        # and it must not knock the filter out of string state.
        m = feed([b"A\x1b_Gf=100;a=T;esc:\x1b[4:3mB\x1b[C" + ST + b"B"])
        self.assertEqual(row0(m), "AB")
        row = [m.screen.buffer[0][x] for x in range(m.cols)]
        self.assertFalse(any(c.underscore or c.italics for c in row),
                         "a lookalike inside the payload was acted on")

    def test_the_next_sequence_after_a_swallowed_string_still_works(self):
        m = feed([b"A" + KITTY_SEQ + b"\x1b[4:3mX"])
        self.assertEqual(row0(m), "AX")
        self.assertTrue(m.screen.buffer[0][1].underscore,
                        "the filter lost sync after a swallowed string")

    # -- boundedness --------------------------------------------------------
    def test_unterminated_payload_is_silent_and_bounded(self):
        # 256 KiB of base64 with no terminator: nothing drawn, nothing buffered,
        # no hang, and the bytes do not resurface when the tail finally lands.
        m = feed([b"A", b"\x1b_Gf=100;a=T;m=1;"], cols=200, rows=2)
        before = state(m)
        for _ in range(256):
            m.feed(b"QUFB" * 1024)
        self.assertEqual(row0(m), "A")
        self.assertEqual(state(m), before,
                         "payload bytes accumulated into observable state")
        self.assertEqual(len(m.stream._csi), 0,
                         "the filter buffered an unbounded amount of payload")
        m.feed(ST + b"B")                                   # the tail finally lands
        self.assertEqual(row0(m), "AB")
        self.assertNotIn("QUFB", m.display[0])

    # -- the counterweight: OSC must keep working --------------------------
    def test_osc_window_title_still_works(self):
        for terminator, label in ((b"\x07", "BEL"), (ST, "ST")):
            with self.subTest(label):
                m = feed([b"A\x1b]0;my title" + terminator + b"B"])
                self.assertEqual(m.title, "my title")
                self.assertEqual(row0(m), "AB")
        m = feed([b"\x1b]2;icon and title\x07"])
        self.assertEqual(m.title, "icon and title")

    def test_osc_hyperlink_still_works(self):
        m = feed([b"\x1b]8;;https://example.com" + ST + b"link"
                  b"\x1b]8;;" + ST + b" done"])
        self.assertEqual(row0(m), "link done",
                         "OSC 8 stopped consuming its payload")

    def test_osc_payload_lookalike_is_preserved_verbatim(self):
        # The rule the DCS case shares: bytes inside a string belong to the
        # application and must reach pyte byte for byte.
        m = feed([b"\x1b]0;t\x1b[4:3mx\x07AFTER"])
        self.assertEqual(m.title, "t\x1b[4:3mx")
        self.assertEqual(row0(m), "AFTER")

    def test_osc_1337_inline_image_stays_off_the_grid(self):
        m = feed([OSC_1337])
        self.assertEqual(row0(m), "AB")
        self.assertNotIn("QUFBQQ", m.display[0])

    def test_plain_text_around_a_string_is_never_disturbed(self):
        # Guard against the filter eating a byte too many on the way out of a
        # swallowed string: both neighbours and the cursor must be exact.
        m = feed([b"first" + SIXEL_SEQ + b"last"])
        self.assertEqual(row0(m), "firstlast")
        self.assertEqual(tuple(m.cursor), (0, 9))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
