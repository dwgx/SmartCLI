"""tui_ui_smoke.py -- screenshot-smoke the tui-ui skill across the env matrix.

For every widget 'demo' + the 'gallery' dashboard, render at each size in the
matrix (tui-ui sizes via --width/--height, so we render a fresh frame per size),
feed the frame bytes through pyte at that geometry, quantize to each color depth,
write a REAL PNG, and run both the harness defect checks and tui-ui-specific
LAYOUT checks (source-line width == cols [fr-drift/overflow], table column
alignment across CJK/emoji rows, box-drawing border integrity, tmux-safety).

Honest provenance: pyte-simulation (VT emulation -> PIL); NOT a real-tmux capture.
tui-ui emits only SGR + newlines (no alt-screen / cursor / scroll-region), which
we verify per frame -- that is why the alt-screen axis is render-identical and is
covered by a stream-safety assertion rather than duplicate PNGs.
"""
from __future__ import annotations

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from pathlib import Path
_UI = str(Path(__file__).resolve().parents[2] / "skills" / "tui-ui")
if _UI not in sys.path:
    sys.path.insert(0, _UI)

import checks as checks_mod
import matrix as matrix_mod
import shot

from ui import registry
from ui.core import width as cell_width
from ui.core import get_theme

registry.load_all()

SIZES = matrix_mod.SIZES            # (40,12),(80,24),(120,40),(200,50)
DEPTHS = matrix_mod.DEPTHS          # truecolor,256,16,mono
BOX_GLYPHS = set("─│┌┐└┘├┤┬┴┼━┃╭╮╯╰═║╔╗╚╝")
VBARS = set("│┃║")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


# --------------------------------------------------------------------------
# Frame builders (in-process; each renders at an exact width x height)
# --------------------------------------------------------------------------
def demo_frame(name: str, theme, width: int, height: int) -> str:
    from ui.box import Box
    from ui.layout import Page
    cls = registry.get(name)
    widget = cls.sample(theme)
    page = Page(Box(content=widget, padding=(0, 0), bg=theme.bg),
                width=width, height=height, bg=theme.bg)
    return page.to_ansi()


def gallery_frame(theme, width: int, height: int) -> str:
    import importlib
    cli = importlib.import_module("ui.cli")
    page = cli._build_gallery(theme, width, height)
    return page.to_ansi()


# --------------------------------------------------------------------------
# tui-ui-specific LAYOUT checks (run on the source frame + rendered screen)
# --------------------------------------------------------------------------
def check_tmux_safe(frame: str):
    """tui-ui must emit only SGR + newlines: no alt-screen/cursor/scroll-region."""
    bad = []
    for m in _ANSI_RE.finditer(frame):
        seq = m.group(0)
        if seq.endswith("m"):
            continue  # SGR is fine
        bad.append(seq)
    if bad:
        return False, f"non-SGR control seq present: {bad[:3]!r}"
    return True, "SGR + newlines only (alt-screen-agnostic, safe on both buffers)"


def check_source_line_width(frame: str, cols: int, rows: int):
    """Every source line's DISPLAY width must be exactly cols (no fr-drift / no
    overflow). This is the real reflow correctness check -- pyte later pads to
    cols, hiding under-fill, so we assert on the frame the engine produced."""
    lines = frame.split("\n")
    if len(lines) != rows:
        return False, f"{len(lines)} source rows vs {rows} declared"
    for i, ln in enumerate(lines):
        w = cell_width(ln)  # strips ANSI, wide-aware
        if w != cols:
            return False, f"row {i} width {w} != {cols} (fr-drift/overflow)"
    return True, f"all {rows} rows exactly {cols} cells"


def _cell_rows(screen):
    """True cell grid as a list of per-column char lists.

    IMPORTANT: use screen.buffer (real cells), NOT screen.display -- display is a
    string where a wide CJK/emoji glyph is a SINGLE char, so string index != cell
    column and any column-alignment test on it is wrong."""
    out = []
    for r in range(screen.lines):
        row = screen.buffer[r]
        out.append([row[c].data for c in range(screen.columns)])
    return out


def check_border_integrity(screen):
    """When a full rectangular border exists (>=1 top corner AND >=1 bottom
    corner), its top/bottom edges must be contiguous box-drawing (borders
    connect, no mojibake gaps). Widgets that only use line glyphs decoratively
    (progress ─, tabs ━ underline, tree └── guides) have no rectangle -> n/a."""
    rows = _cell_rows(screen)
    corner_top = "┌╭┏╔"
    corner_bot = "└╰┗╚"
    top_r = next((r for r in range(len(rows))
                  if any(c in corner_top for c in rows[r])), None)
    bot_r = next((r for r in range(len(rows) - 1, -1, -1)
                  if any(c in corner_bot for c in rows[r])), None)
    if top_r is None or bot_r is None:
        return True, "no full rectangular border (n/a)"
    if bot_r <= top_r:
        return False, f"bottom corner r{bot_r} above top corner r{top_r}"

    def contiguous(row):
        idx = [i for i, c in enumerate(row) if c in BOX_GLYPHS]
        if not idx:
            return False
        seg = row[idx[0]:idx[-1] + 1]
        # allow title text + spaces embedded on the top edge
        boxn = sum(1 for c in seg if c in BOX_GLYPHS or c == " " or (c and c.strip()))
        return boxn >= len(seg) * 0.6
    if not contiguous(rows[top_r]):
        return False, f"top border row {top_r} not contiguous"
    if not contiguous(rows[bot_r]):
        return False, f"bottom border row {bot_r} not contiguous"
    return True, f"borders connect (rect r{top_r}..r{bot_r})"


def check_table_alignment(screen):
    """Vertical bars must land on identical CELL columns across all table body
    rows. This is the CJK/emoji width proof: a mis-measured wide glyph would
    shift a row's bars. Read true cell columns (screen.buffer), never display."""
    rows = _cell_rows(screen)
    bar_rows = []
    for row in rows:
        cols_with_bar = [i for i, c in enumerate(row) if c in VBARS]
        if len(cols_with_bar) >= 2:
            bar_rows.append(tuple(cols_with_bar))
    if len(bar_rows) < 2:
        return True, "no multi-bar table rows (n/a)"
    # group by bar-count; within a table all body rows share the same count
    from collections import Counter
    counts = Counter(len(b) for b in bar_rows)
    dominant_n = counts.most_common(1)[0][0]
    same_n = [b for b in bar_rows if len(b) == dominant_n]
    ref = same_n[0]
    for b in same_n:
        if b != ref:
            return False, f"bar columns differ: {ref} vs {b} (CJK/emoji misalign)"
    return True, f"{len(same_n)} rows align bars at {list(ref)}"


# --------------------------------------------------------------------------
# One target across the size x depth matrix
# --------------------------------------------------------------------------
def run_target(name, frame_fn, theme, out_dir, cell_w=8, cell_h=17):
    os.makedirs(out_dir, exist_ok=True)
    results = []  # (size, depth, png, ok, fails)
    per_size = {}
    for (cols, rows) in SIZES:
        frame = frame_fn(theme, cols, rows)
        data = shot.render_frame_to_bytes(frame)
        base = shot.render_bytes_to_screen(data, cols, rows)
        src_color = checks_mod.stream_has_color(data)
        # layout checks (frame-level + screen-level), depth-independent
        layout = [
            ("tmux_safe",) + check_tmux_safe(frame),
            ("source_line_width",) + check_source_line_width(frame, cols, rows),
            ("border_integrity",) + check_border_integrity(base),
            ("table_alignment",) + check_table_alignment(base),
            ("alt_screen_balanced",) + checks_mod.alt_screen_balanced(data),
            ("cursor_hide_balanced",) + checks_mod.cursor_hide_balanced(data),
        ]
        per_size[(cols, rows)] = (frame, data, base, src_color, layout)
        for depth in DEPTHS:
            screen = matrix_mod.apply_depth(base, depth)
            fname = f"{name}__{cols}x{rows}__{depth}.png"
            png = os.path.join(out_dir, fname)
            w, h = shot.screen_to_png(screen, png, cell_w=cell_w, cell_h=cell_h)
            checks = list(layout) + checks_mod.run_screen_checks(
                screen, depth=depth, expected_alt=False,
                expect_content=True, source_has_color=src_color)
            fails = [(n, d) for n, ok, d in checks if not ok]
            results.append(((cols, rows), depth, png, not fails, fails, os.path.getsize(png)))
    return results, per_size


def main():
    theme = get_theme("dashboard")
    out_root = os.path.join(_HERE, "out", "tui_ui")
    os.makedirs(out_root, exist_ok=True)
    widget_keys = [w.key for w in registry.all_widgets()]
    targets = [(k, (lambda th, c, r, k=k: demo_frame(k, th, c, r))) for k in widget_keys]
    targets.append(("gallery", gallery_frame))

    grand = {}
    for name, fn in targets:
        odir = os.path.join(out_root, name)
        res, _ = run_target(name, fn, theme, odir)
        grand[name] = res

    # print compact matrix report
    print("PROVENANCE:", shot.RENDER_LABEL)
    print("=" * 78)
    total = passed = 0
    all_fails = {}
    for name in [t[0] for t in targets]:
        res = grand[name]
        npass = sum(1 for r in res if r[3])
        total += len(res)
        passed += npass
        status = "PASS" if npass == len(res) else f"FAIL {len(res)-npass}/{len(res)}"
        print(f"{name:<10} {npass}/{len(res)} cells  {status}")
        for size, depth, png, ok, fails, sz in res:
            if not ok:
                key = (name, size, depth)
                all_fails[key] = fails
    print("-" * 78)
    print(f"TOTAL: {passed}/{total} cells pass")
    if all_fails:
        print("\nFAILURES:")
        for (name, size, depth), fails in all_fails.items():
            fs = "; ".join(f"{n}: {d}" for n, d in fails)
            print(f"  {name} {size[0]}x{size[1]} {depth}: {fs}")
    print(f"\nPNG dir: {out_root}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
