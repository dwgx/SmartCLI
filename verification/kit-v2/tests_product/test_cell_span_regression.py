"""T05 real-core regression. Copy to repo/tests or pass --repo explicitly.
No PTY. Expected labels are literal test data, not computed by production helpers.
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
    if not imported or not Path(imported).resolve().is_relative_to((args.repo.resolve() / "smartcli_core")):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)


class CellSpanRegression(unittest.TestCase):
    def check_label(self, payload: str, expected: str) -> None:
        model = ScreenModel(cols=60, rows=4)
        model.feed(payload.encode("utf-8"))
        before = list(model.display)
        snap = build_snapshot(model)
        self.assertIsNotNone(snap.selected)
        self.assertEqual(snap.selected.text, expected)
        self.assertIn(expected, [s.text for s in snap.menu_items])
        structured = json.loads(snap.to_json())
        self.assertEqual(structured["selected"]["text"], expected)
        self.assertIn(expected, snap.to_text())
        self.assertEqual(before, model.display, "snapshot must not redraw the screen")

    def test_real_chinese_menu(self):
        self.check_label("  1) 打开   2) \x1b[7m保存\x1b[0m   3) 退出\n", "保存")

    def test_ascii_control(self):
        self.check_label("  1) Open   2) \x1b[7mSave\x1b[0m   3) Quit", "Save")

    def test_cjk_prefix_ascii_label(self):
        self.check_label("中文 \x1b[7mOK\x1b[0m tail", "OK")

    def test_japanese_prefix(self):
        self.check_label("日本語 \x1b[7m保存\x1b[0m tail", "保存")

    def test_emoji_prefix(self):
        self.check_label("🚀 \x1b[7mOK\x1b[0m tail", "OK")

    def test_combining_prefix(self):
        self.check_label("e\u0301 \x1b[7mOK\x1b[0m tail", "OK")

    def test_wide_at_zero_with_following_text(self):
        self.check_label("\x1b[7m中文\x1b[0mXY", "中文")

    def test_label_whitespace_unchanged(self):
        self.check_label("前缀 \x1b[7m 保存 \x1b[0m trailing", "保存")

    def test_repeated_labels_do_not_define_the_oracle(self):
        self.check_label("保存 \x1b[7m保存\x1b[0m 保存", "保存")

if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
