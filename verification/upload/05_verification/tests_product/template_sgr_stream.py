"""T04 tests: partition invariance AND independent supported-SGR semantics.
No PTY. Add implementation-specific overflow/string-state tests in this file.
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
    if not imported or not Path(imported).resolve().is_relative_to((args.repo.resolve() / "smartcli_core")):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)


def state(model):
    return (tuple(tuple(tuple(model.screen.buffer[y][x]) for x in range(model.cols))
                  for y in range(model.rows)), model.cursor, model.cursor_hidden,
            model.title, model.alt_screen, model.app_cursor)


def feed(chunks):
    model = ScreenModel(cols=30, rows=4)
    for chunk in chunks: model.feed(chunk)
    return model


class SgrStreamRegression(unittest.TestCase):
    def assert_partition_safe(self, payload):
        expected = state(feed([payload]))
        for cut in range(1, len(payload)):
            with self.subTest(cut=cut, payload=payload):
                self.assertEqual(state(feed([payload[:cut], payload[cut:]])), expected)
        self.assertEqual(state(feed([payload[i:i+1] for i in range(len(payload))])), expected)
        for seed in range(4):
            rng = random.Random(seed); chunks = []; i = 0
            while i < len(payload):
                n = rng.randint(1, 7); chunks.append(payload[i:i+n]); i += n
            self.assertEqual(state(feed(chunks)), expected)

    def test_subparameter_vectors(self):
        for p in [b"\x1b[4:3mX", b"\x1b[38:2::255:0:128mX", b"\x1b[48:2::0:255:0mX",
                  b"\x1b[58:2::1:2:3mX", "\x1b[1;38:2::12:34:56m中文\x1b[0m".encode()]:
            self.assert_partition_safe(p)

    def test_controls(self):
        for p in [b"\x1b[31mX", b"\x1b[2;5HX", "\x1b]0;标题\x07中文".encode(),
                  b"\x1b[?1049hALT\x1b[?1049l", b"\x1b[?1h"]:
            self.assert_partition_safe(p)

    def test_truecolor_semantics(self):
        m = feed([b"\x1b[38:2::255:0:128mX"])
        self.assertEqual(m.screen.buffer[0][0].fg, "ff0080")
        self.assertEqual(m.display[0].rstrip(), "X")

    def test_curly_underline_degrades_without_italic(self):
        m = feed([b"\x1b[4:3mX"])
        self.assertTrue(m.screen.buffer[0][0].underscore)
        self.assertFalse(m.screen.buffer[0][0].italics)

    def test_unsupported_underline_color_must_not_change_fg(self):
        m = feed([b"\x1b[31;58:2::1:2:3mX"])
        self.assertEqual(m.screen.buffer[0][0].fg, "red")
        self.assertFalse(m.screen.buffer[0][0].italics)
        self.assertEqual(m.display[0].rstrip(), "X")

if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
