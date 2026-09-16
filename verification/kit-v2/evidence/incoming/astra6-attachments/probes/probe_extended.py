"""Extended local evidence for the CJK cell-span defect (A03) and SGR split (A02).

Pure in-memory, imports smartcli_core from the checkout. Writes nothing to the repo.
Run: python probe_extended.py <repo-root>
"""
from __future__ import annotations

import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else r"D:\Project\SmartCLI"
sys.path.insert(0, REPO)

from smartcli_core.screen_model import ScreenModel  # noqa: E402
from smartcli_core.snapshot import build_snapshot  # noqa: E402


def cell_span_text(model: ScreenModel, row: int, a: int, b: int) -> str:
    """What the snapshot SHOULD return: text aggregated over the cell span."""
    cells = model.row_cells(row)
    return "".join(c.data for c in cells[a:b]).rstrip()


def show(label: str, text: str, a: int, b: int) -> None:
    m = ScreenModel(cols=40, rows=3)
    m.feed(text.encode("utf-8"))
    line = m.display[0]
    want = cell_span_text(m, 0, a, b)
    got = line[a:b].strip()
    flag = "same" if want == got else "WRONG"
    print(f"  {label:<28} cells[{a}:{b}] want={want!r:<10} snapshot-rule-gives={got!r:<10} {flag}")


print("== which rows break the display[a:b] rule (snapshot.py line ~264) ==")
show("pure ASCII", "abcdefgh OK", 9, 11)
show("CJK prefix", "中文 OK", 4, 7)
show("Japanese + ASCII", "日本語テスト OK", 12, 14)
show("emoji before", "🚀🚀 OK", 4, 7)
show("combining mark", "e\u0301xe\u0301 OK", 6, 8)
show("full-width digits", "１２３OK", 5, 7)
show("wide inside span", "\x1b[7m中文OK\x1b[0m", 0, 6)

print("\n== end-to-end: build_snapshot on a CJK menu (the field an agent actually reads) ==")
for label, payload in (
    ("CJK label then highlighted ASCII",
     "选项：中文 OK\n"),
    ("menu, reverse video over '保存'",
     "  1) 打开   2) \x1b[7m保存\x1b[0m   3) 退出\n"),
):
    m = ScreenModel(cols=40, rows=5)
    m.feed(payload.encode("utf-8"))
    snap = build_snapshot(m)
    print(f"  {label}")
    for s in snap.menu_items:
        truth = cell_span_text(m, s.row, s.col_start, s.col_end)
        mark = "same" if s.text == truth else "WRONG"
        print(f"    span r{s.row}[{s.col_start}:{s.col_end}] "
              f"reported={s.text!r} truth={truth!r} {mark}")
    if snap.selected:
        truth = cell_span_text(m, snap.selected.row, snap.selected.col_start, snap.selected.col_end)
        print(f"    selected.text={snap.selected.text!r} truth={truth!r}")

print("\n== A02: SGR split sweep across every byte boundary (all payloads) ==")
payloads = {
    "curly underline": b"\x1b[4:3mX",
    "truecolor fg": b"\x1b[38:2::255:0:0mX",
    "truecolor bg": b"\x1b[48:2::0:255:0mX",
    "underline colour": b"\x1b[58:2::1:2:3mX",
    "plain SGR (control)": b"\x1b[31mX",
    "CSI cursor move (control)": b"\x1b[10;5HX",
    "OSC title (control)": b"\x1b]0;hello\x07X",
}
for label, payload in payloads.items():
    ref = ScreenModel(cols=30, rows=3)
    ref.feed(payload)
    ref_line = ref.display[0]
    diverging = []
    for cut in range(1, len(payload)):
        s = ScreenModel(cols=30, rows=3)
        s.feed(payload[:cut])
        s.feed(payload[cut:])
        if s.display[0] != ref_line:
            diverging.append(cut)
    verdict = "SPLIT-SAFE" if not diverging else f"BROKEN at {len(diverging)}/{len(payload)-1} cuts"
    print(f"  {label:<26} {verdict:<26} first_bad={diverging[0] if diverging else '-'}")

print("\n== A02: does random chunking break real text? (10 trials, 1-7 byte chunks) ==")
import random  # noqa: E402

random.seed(7)
sample = ("\x1b[38:2::255:0:0m红色\x1b[0m \x1b[4:3m下划线\x1b[0m done\n").encode("utf-8")
ref = ScreenModel(cols=60, rows=3)
ref.feed(sample)
ref_line = ref.display[0]
bad = 0
for trial in range(10):
    m = ScreenModel(cols=60, rows=3)
    i = 0
    while i < len(sample):
        n = random.randint(1, 7)
        m.feed(sample[i:i + n])
        i += n
    if m.display[0] != ref_line:
        bad += 1
        if bad == 1:
            print(f"    trial {trial}: {m.display[0]!r}")
print(f"  reference={ref_line!r}")
print(f"  trials that diverge: {bad}/10")
