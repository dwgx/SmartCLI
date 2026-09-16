"""Local re-verification of the web audit's A01-A03 claims against SmartCLI @701e61f.

Read-only: imports smartcli_core from the checkout, runs pure in-memory checks,
writes nothing into the repo. Run: python probe_core.py <repo-root>
"""
from __future__ import annotations

import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else r"D:\Project\SmartCLI"
sys.path.insert(0, REPO)

from smartcli_core.screen_model import ScreenModel  # noqa: E402
from smartcli_core.snapshot import build_snapshot  # noqa: E402

print("== A03: cell-column span vs string slice on a CJK row ==")
m = ScreenModel(cols=20, rows=3)
# reverse-video run over the two cells of "OK" (each ASCII = 1 cell)
m.feed("中文 OK".encode("utf-8"))
line = m.display[0]
print(f"  display[0]={line!r} len={len(line)} cols={m.screen.columns}")
cells = m.row_cells(0)
print(f"  cells[0:8]={[c.data for c in cells[:8]]}")
# emulate snapshot.py's build_snapshot highlight extraction for a 2-cell span
a, b = 5, 7  # cell columns of "OK" on this row
cell_text = "".join(c.data for c in cells[a:b]).strip()
str_slice = line[a:b].strip()
print(f"  span cell-aggregate  cell_span_text({a},{b}) -> {cell_text!r}")
print(f"  span string slice    display[0][{a}:{b}]    -> {str_slice!r}")
print(f"  MATCH={cell_text == str_slice}")

print("\n== A03b: what build_snapshot actually reports for a CJK menu row ==")
m2 = ScreenModel(cols=20, rows=3)
m2.feed("中文 \x1b[7mOK\x1b[0m ✓".encode("utf-8"))
snap = build_snapshot(m2)
for s in snap.menu_items:
    print(f"  menu span row={s.row} [{s.col_start}:{s.col_end}] text={s.text!r}")
print(f"  selected={snap.selected}")
print(f"  to_text header: {snap.to_text().splitlines()[0]}")

print("\n== A03c: same row, wide char inside the highlighted span ==")
m3 = ScreenModel(cols=20, rows=3)
m3.feed("\x1b[7m中文OK\x1b[0m".encode("utf-8"))
snap3 = build_snapshot(m3)
for s in snap3.menu_items:
    print(f"  menu span [{s.col_start}:{s.col_end}] text={s.text!r}")
truth = "".join(c.data for c in m3.row_cells(0)[0:6]).strip()
print(f"  cell-truth for [0:6] = {truth!r}")

print("\n== A02: SGR sub-parameter (colon) split across feed() boundaries ==")
whole = ScreenModel(cols=20, rows=2)
whole.feed(b"\x1b[4:3mX")
split = ScreenModel(cols=20, rows=2)
split.feed(b"\x1b[4:")
split.feed(b"3mX")
print(f"  one chunk  : display[0]={whole.display[0]!r}")
print(f"  split feed : display[0]={split.display[0]!r}")
print(f"  IDENTICAL={whole.display[0] == split.display[0]}")

print("\n== A02b: every byte boundary (systematic split sweep) ==")
payload = b"\x1b[38:2::255:0:0mZ"
ref = ScreenModel(cols=20, rows=2)
ref.feed(payload)
ref_line = ref.display[0]
bad = []
for cut in range(1, len(payload)):
    s = ScreenModel(cols=20, rows=2)
    s.feed(payload[:cut])
    s.feed(payload[cut:])
    if s.display[0] != ref_line:
        bad.append((cut, s.display[0]))
print(f"  payload={payload!r} reference={ref_line!r}")
print(f"  diverging split points: {len(bad)}/{len(payload) - 1}")
for cut, out in bad[:6]:
    print(f"    cut={cut}: {out!r}")

print("\n== A02c: byte-by-byte feed (worst case) ==")
bytewise = ScreenModel(cols=20, rows=2)
for i in range(len(payload)):
    bytewise.feed(payload[i:i + 1])
print(f"  bytewise   : {bytewise.display[0]!r}")
print(f"  IDENTICAL={bytewise.display[0] == ref_line}")

print("\n== A04-preview: feed_errors counter on split SGR ==")
s = ScreenModel(cols=20, rows=2)
s.feed(b"\x1b[4:")
s.feed(b"3mX")
print(f"  feed_errors={s.feed_errors}")
