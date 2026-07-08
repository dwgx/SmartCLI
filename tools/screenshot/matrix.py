"""matrix.py -- environment matrix + color-depth downsampling + contact sheets.

Defines the environment matrix the harness sweeps and a runner that, for one
target's raw byte stream, produces one PNG per (size, depth) cell plus an HTML
and a Markdown contact-sheet index that links every PNG.

Color-depth downsampling
-------------------------
A program emits whatever colors it likes; a real terminal (or tmux) then
*degrades* them to its advertised depth. We reproduce that on the rendered
pyte Screen by re-quantizing each cell's fg/bg:
  * ``truecolor`` -- unchanged (24-bit).
  * ``256``       -- snap RGB to the nearest xterm-256 palette entry.
  * ``16``        -- snap RGB to the nearest of the 16 ANSI colors.
  * ``mono``      -- luminance threshold to fg/bg only.
Re-quantizing the *rendered grid* (not the byte stream) means each depth
screenshots faithfully without re-running the target.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pyte

import shot

# --------------------------------------------------------------------------
# The environment matrix
# --------------------------------------------------------------------------
SIZES: List[Tuple[int, int]] = [(40, 12), (80, 24), (120, 40), (200, 50)]
DEPTHS: List[str] = ["truecolor", "256", "16", "mono"]
ALT_SCREEN_MODES: List[bool] = [True, False]

# Content edge-case fixtures (fed as raw bytes) used by the self-test / demo.
CONTENT_EDGE_CASES: Dict[str, bytes] = {
    "cjk_wide": "CJK: 你好世界 日本語".encode("utf-8"),
    "emoji": "emoji: \U0001f600 \U0001f680 \U0001f4a5 ❤".encode("utf-8"),
    "box_drawing": (
        "┌──┐\r\n│ok│\r\n└──┘"
    ).encode("utf-8"),
    "long_line": (b"X" * 300),
}

# xterm-256 palette as RGB triples (pyte ships the hex strings).
_PALETTE_256: List[Tuple[int, int, int]] = [
    (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    for h in pyte.graphics.FG_BG_256
]
_ANSI16 = _PALETTE_256[:16]


# --------------------------------------------------------------------------
# Color quantization
# --------------------------------------------------------------------------
def _nearest(rgb: Tuple[int, int, int], palette: Sequence[Tuple[int, int, int]]) -> int:
    r, g, b = rgb
    best_i, best_d = 0, 1 << 30
    for i, (pr, pg, pb) in enumerate(palette):
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def _to_hex(rgb: Tuple[int, int, int]) -> str:
    return "%02x%02x%02x" % rgb


def quantize_color(color: str, depth: str, *, is_bg: bool) -> str:
    """Downsample one pyte color string to ``depth``. Keeps ``"default"`` intact."""
    if depth == "truecolor" or color == "default" or not color:
        return color
    rgb = shot.color_to_rgb(color, is_bg=is_bg)
    if depth == "256":
        return _to_hex(_PALETTE_256[_nearest(rgb, _PALETTE_256)])
    if depth == "16":
        return _to_hex(_ANSI16[_nearest(rgb, _ANSI16)])
    if depth == "mono":
        lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
        return "000000" if lum < 110 else "e5e5e5"
    return color


def apply_depth(screen: pyte.Screen, depth: str) -> pyte.Screen:
    """Return a NEW screen with every cell's colors quantized to ``depth``.

    Rebuilds a fresh Screen of the same geometry and copies each Char with
    downsampled fg/bg (data + bold/reverse/underscore preserved). truecolor is
    a straight copy.
    """
    cols, rows = screen.columns, screen.lines
    out = pyte.Screen(cols, rows)
    if depth == "truecolor":
        for row in range(rows):
            src = screen.buffer[row]
            for col in range(cols):
                out.buffer[row][col] = src[col]
        out.cursor.x, out.cursor.y = screen.cursor.x, screen.cursor.y
        out.cursor.hidden = screen.cursor.hidden
        return out
    for row in range(rows):
        src = screen.buffer[row]
        for col in range(cols):
            ch = src[col]
            out.buffer[row][col] = ch._replace(
                fg=quantize_color(ch.fg, depth, is_bg=False),
                bg=quantize_color(ch.bg, depth, is_bg=True),
            )
    out.cursor.x, out.cursor.y = screen.cursor.x, screen.cursor.y
    out.cursor.hidden = screen.cursor.hidden
    return out


# --------------------------------------------------------------------------
# Target + run results
# --------------------------------------------------------------------------
@dataclass
class Target:
    """One thing to screenshot: a name + the raw bytes it produced."""

    name: str
    data: bytes
    alt_screen: bool = False
    label: str = shot.RENDER_LABEL


@dataclass
class CellResult:
    size: Tuple[int, int]
    depth: str
    png_path: str
    width_px: int
    height_px: int
    checks: List[Tuple[str, bool, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------
def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)


def run_matrix(
    target: Target,
    out_dir: str,
    *,
    sizes: Optional[List[Tuple[int, int]]] = None,
    depths: Optional[List[str]] = None,
    font_path: str = shot.DEFAULT_FONT,
    cell_w: int = 9,
    cell_h: int = 19,
    run_checks: bool = True,
) -> List[CellResult]:
    """Render ``target`` across the (size x depth) matrix into ``out_dir``.

    Produces one PNG per cell (named ``<target>__<cols>x<rows>__<depth>.png``),
    runs the automated defect checks on each rendered screen, then writes
    ``index.html`` and ``index.md`` contact sheets. Returns the per-cell results.
    """
    import checks as checks_mod

    sizes = sizes or SIZES
    depths = depths or DEPTHS
    os.makedirs(out_dir, exist_ok=True)
    results: List[CellResult] = []

    # Stream-level checks (byte scan) run once -- they don't depend on size/depth.
    stream_checks = checks_mod.run_stream_checks(target.data) if run_checks else []
    src_color = checks_mod.stream_has_color(target.data)

    for (cols, rows) in sizes:
        base_screen = shot.render_bytes_to_screen(target.data, cols, rows)
        for depth in depths:
            screen = apply_depth(base_screen, depth)
            fname = f"{_slug(target.name)}__{cols}x{rows}__{depth}.png"
            png_path = os.path.join(out_dir, fname)
            w, h = shot.screen_to_png(
                screen, png_path, font_path=font_path,
                cell_w=cell_w, cell_h=cell_h,
            )
            cell_checks: List[Tuple[str, bool, str]] = list(stream_checks)
            if run_checks:
                cell_checks += checks_mod.run_screen_checks(
                    screen, depth=depth, expected_alt=target.alt_screen,
                    source_has_color=src_color,
                )
            results.append(CellResult((cols, rows), depth, png_path, w, h, cell_checks))

    write_contact_sheets(target, results, out_dir)
    return results


# --------------------------------------------------------------------------
# Contact sheets
# --------------------------------------------------------------------------
def write_contact_sheets(target: Target, results: List[CellResult], out_dir: str) -> Tuple[str, str]:
    """Write ``index.html`` and ``index.md`` linking every PNG. Returns their paths."""
    html_path = os.path.join(out_dir, "index.html")
    md_path = os.path.join(out_dir, "index.md")

    sizes = sorted({r.size for r in results}, key=lambda s: (s[0], s[1]))
    depths = []
    for r in results:
        if r.depth not in depths:
            depths.append(r.depth)
    by_key = {(r.size, r.depth): r for r in results}

    def rel(p: str) -> str:
        return os.path.basename(p)

    # --- HTML ---
    rows_html = []
    for size in sizes:
        cells = []
        for depth in depths:
            r = by_key.get((size, depth))
            if not r:
                cells.append("<td></td>")
                continue
            badge = "PASS" if r.ok else "FAIL"
            cls = "pass" if r.ok else "fail"
            fails = [f"{n}: {d}" for n, ok, d in r.checks if not ok]
            title = " | ".join(fails) if fails else "all checks passed"
            cells.append(
                f'<td class="{cls}"><div class="cap">{depth} '
                f'<span class="badge {cls}">{badge}</span></div>'
                f'<a href="{rel(r.png_path)}"><img src="{rel(r.png_path)}" '
                f'title="{_esc(title)}"></a></td>'
            )
        rows_html.append(
            f'<tr><th>{size[0]}x{size[1]}</th>{"".join(cells)}</tr>')
    header_cells = "".join(f"<th>{d}</th>" for d in depths)
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>screenshot matrix: {_esc(target.name)}</title>
<style>
 body{{background:#111;color:#ddd;font-family:Consolas,monospace;padding:16px}}
 table{{border-collapse:collapse}} td,th{{border:1px solid #333;padding:6px;vertical-align:top}}
 img{{max-width:340px;display:block;background:#000}}
 .cap{{font-size:12px;margin-bottom:4px}}
 .badge{{padding:1px 5px;border-radius:3px;font-size:11px}}
 .badge.pass{{background:#1a5}}.badge.fail{{background:#c33}}
 td.fail{{outline:2px solid #c33}}
 .label{{color:#e90;margin:8px 0}}
</style></head><body>
<h2>Screenshot matrix: {_esc(target.name)}</h2>
<p class="label">RENDER PROVENANCE: {_esc(target.label)}</p>
<table><tr><th>size \\ depth</th>{header_cells}</tr>
{chr(10).join(rows_html)}
</table></body></html>"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # --- Markdown ---
    lines = [
        f"# Screenshot matrix: {target.name}",
        "",
        f"**RENDER PROVENANCE:** {target.label}",
        "",
        "| size \\ depth | " + " | ".join(depths) + " |",
        "|" + "---|" * (len(depths) + 1),
    ]
    for size in sizes:
        row = [f"{size[0]}x{size[1]}"]
        for depth in depths:
            r = by_key.get((size, depth))
            if not r:
                row.append("")
                continue
            status = "PASS" if r.ok else "FAIL"
            row.append(f"[{status}]({rel(r.png_path)})")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "## Check details", ""]
    for r in results:
        fails = [f"{n} ({d})" for n, ok, d in r.checks if not ok]
        tag = "PASS" if r.ok else "FAIL: " + "; ".join(fails)
        lines.append(f"- `{os.path.basename(r.png_path)}` -- {tag}")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return html_path, md_path


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
