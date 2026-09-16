"""T05 regression: highlighted-span labels must be aggregated over CELLS.

A terminal column index is not a string index. `display[y][a:b]` slices a
Unicode string with cell coordinates, so any wide glyph (CJK, kana, emoji,
fullwidth digits) to the LEFT of a highlighted span shifts the slice: the real
Chinese menu below reported the selected label as ``3`` when the highlighted
item was ``保存``. Pure memory: no PTY, no process, no fixture file.

Expected labels are literal test data. They are deliberately NOT computed with
the production aggregation helper -- an oracle that calls the code under test
would pass with the bug still in place. Controls that the old string slice
happened to get right (ASCII, a span that starts at column 0) are pinned so the
fix cannot buy the wide-character cases by changing something else.

Run: python tests/test_cell_span_regression.py [--repo PATH]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unittest

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
sys.dont_write_bytecode = True
sys.path.insert(0, str(args.repo.resolve()))
try:
    from smartcli_core.screen_model import ScreenModel
    from smartcli_core.snapshot import build_snapshot
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to(
            (args.repo.resolve() / "smartcli_core")):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)


class CellSpanRegression(unittest.TestCase):
    def check_label(self, payload: str, expected: str, cols: int = 60) -> None:
        """The highlighted span must read `expected`, in every output surface."""
        model = ScreenModel(cols=cols, rows=4)
        model.feed(payload.encode("utf-8"))
        before = list(model.display)
        snap = build_snapshot(model)
        self.assertIsNotNone(snap.selected, "no highlighted span was detected")
        self.assertEqual(snap.selected.text, expected, "snapshot.selected.text")
        self.assertIn(expected, [s.text for s in snap.menu_items], "menu_items[].text")
        structured = json.loads(snap.to_json())
        self.assertEqual(structured["selected"]["text"], expected, "to_json()['selected']['text']")
        self.assertIn(expected, snap.to_text(), "to_text() header")
        self.assertEqual(before, model.display, "building a snapshot must not redraw the screen")

    # -- the reported defect -------------------------------------------------
    def test_real_chinese_menu(self):
        self.check_label("  1) 打开   2) \x1b[7m保存\x1b[0m   3) 退出\n", "保存")

    def test_span_start_is_a_cell_column(self):
        # The highlight covers two cells; the row already holds two wide glyphs,
        # so the string index of the same span is 15 - 5 = 10 characters earlier.
        model = ScreenModel(cols=60, rows=4)
        model.feed("  1) 打开   2) \x1b[7m保存\x1b[0m   3) 退出\n".encode("utf-8"))
        snap = build_snapshot(model)
        self.assertEqual((snap.selected.col_start, snap.selected.col_end), (15, 19))
        self.assertEqual(snap.selected.text, "保存")

    def test_menu_items_all_match_literal_labels(self):
        model = ScreenModel(cols=60, rows=4)
        model.feed("  1) \x1b[7m打开\x1b[0m   2) \x1b[7m保存\x1b[0m   3) \x1b[7m退出\x1b[0m\n".encode())
        snap = build_snapshot(model)
        self.assertEqual([s.text for s in snap.menu_items], ["打开", "保存", "退出"])

    # -- wide-character families that used to shift the slice ----------------
    def test_ascii_control(self):
        self.check_label("  1) Open   2) \x1b[7mSave\x1b[0m   3) Quit", "Save")

    def test_cjk_prefix_ascii_label(self):
        self.check_label("中文 \x1b[7mOK\x1b[0m tail", "OK")

    def test_japanese_prefix(self):
        self.check_label("日本語 \x1b[7m保存\x1b[0m tail", "保存")

    def test_fullwidth_digit_prefix(self):
        self.check_label("１２３\x1b[7mOK\x1b[0m tail", "OK")

    def test_emoji_prefix(self):
        self.check_label("🚀 \x1b[7mOK\x1b[0m tail", "OK")

    def test_zwj_emoji_prefix(self):
        self.check_label("👨‍👩‍👧 \x1b[7mOK\x1b[0m tail", "OK")

    def test_variation_selector_prefix(self):
        self.check_label("❤️ \x1b[7mOK\x1b[0m tail", "OK")

    def test_combining_prefix(self):
        self.check_label("e\u0301 \x1b[7mOK\x1b[0m tail", "OK")

    def test_four_byte_utf8_prefix_containing_continuation_byte(self):
        # U+4E1B encodes as e4 b8 9b: the 0x9b byte is a UTF-8 continuation,
        # never a C1 control, and must not disturb cell coordinates.
        self.check_label("丛 \x1b[7mOK\x1b[0m tail", "OK")

    # -- boundaries ----------------------------------------------------------
    def test_wide_at_zero_with_following_text(self):
        self.check_label("\x1b[7m中文\x1b[0mXY", "中文")

    def test_span_reaching_the_last_column(self):
        # 9 wide glyphs occupy 18 of 20 cells; the highlight takes the last two
        # without wrapping, so the span ends exactly on the final column.
        self.check_label("中" * 9 + "\x1b[7mXX", "XX", cols=20)

    def test_label_whitespace_unchanged(self):
        # .strip() on the aggregated label is the pre-existing behaviour: the
        # padding cells around a highlight stay out of the label, and interior
        # spaces stay in.
        self.check_label("前缀 \x1b[7m 保存 \x1b[0m trailing", "保存")
        self.check_label("top \x1b[7m保存 文件\x1b[0m end", "保存 文件")

    def test_repeated_labels_do_not_define_the_oracle(self):
        self.check_label("保存 \x1b[7m保存\x1b[0m 保存", "保存")

    # -- the neighbours that must not change --------------------------------
    def test_cursor_line_fallback_is_unchanged(self):
        # With no highlighted span, `selected` falls back to the cursor row and
        # its text is the whole row (no column slicing involved).
        model = ScreenModel(cols=40, rows=4)
        model.feed("中文 prompt 中文".encode("utf-8"))
        snap = build_snapshot(model)
        self.assertEqual(snap.selected_reason, "cursor_line")
        self.assertEqual(snap.selected.text, "中文 prompt 中文")

    def test_body_text_is_not_column_sliced(self):
        model = ScreenModel(cols=40, rows=4)
        model.feed("中文 body 保存 中文\n".encode("utf-8"))
        snap = build_snapshot(model)
        self.assertIn("中文 body 保存 中文", snap.to_text())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
