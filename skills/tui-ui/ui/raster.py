"""raster.py — SubcellRaster: sub-cell resolution (primitive #2).

A terminal cell is the smallest unit the grid can address, so a plain
``cols x rows`` Canvas is forever blocky. The escape hatch is *sub-cell*
glyphs: a single character whose interior is subdivided into fixed pixel
regions, coloured via fg/bg. This module is a tiny off-screen pixel engine
that draws into a real pixel buffer, then downsamples each cell's pixels to
the best matching sub-cell glyph + colours and writes back into a Canvas.
See references/RENDERING-MODEL.md §2. This is "the smooth part" — images,
anti-aliased curves, sparklines, round discs all route through here.

Three densities, and THE load-bearing fact is that in every one of them a
sub-cell pixel comes out SCREEN-SQUARE, because the pixel subdivision cancels
ASPECT=2 (cell height : width):

  * ``half``    -> cols x (rows*2)   1x2 px/cell  -> ▀ (fg=top px, bg=bottom px)
  * ``quad``    -> (cols*2) x (rows*2) 2x2 px/cell -> ▘▝▖▗▀▄▌▐▚▞▛▜▙▟█ + space
  * ``braille`` -> (cols*2) x (rows*4) 2x4 px/cell -> U+2800 + 8-dot mask (densest)

Because the buffer pixels are square, ``circle``/``disc`` take a plain
Euclidean radius and still read round on screen — no per-call ASPECT term
(unlike field.py, where cells ARE the pixels and y must be scaled by ASPECT).
"""
from __future__ import annotations

import sys
from typing import List, Optional, Sequence, Tuple

from .core import RGB, Canvas, parse_color

# ==========================================================================
# Sub-cell glyph tables — the whole "smoothness" trick is these lookups.
# ==========================================================================
# half: 1 col x 2 rows of pixels per cell. Upper-half block ▀ carries the top
# pixel as fg and the bottom pixel as bg, so one cell shows two colours.
HALF_TOP = "▀"      # U+2580 upper half block  (fg = top pixel)
HALF_BOT = "▄"      # U+2584 lower half block  (fg = bottom pixel)
HALF_FULL = "█"     # U+2588 full block        (both pixels same colour)

# quad: 2x2 pixels per cell, indexed by a 4-bit mask (bit0=TL,1=TR,2=BL,3=BR).
QUAD_GLYPHS = [
    " ", "▘", "▝", "▀", "▖", "▌", "▞", "▛",
    "▗", "▚", "▐", "▜", "▄", "▙", "▟", "█",
]

# braille: 2x4 pixels per cell. Dot bit values per (col, row) sub-position —
# the historical 2x4 Braille layout (dots 1-6 then 7-8 on the bottom row).
BRAILLE_BITS = {
    (0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (0, 3): 0x40,
    (1, 0): 0x08, (1, 1): 0x10, (1, 2): 0x20, (1, 3): 0x80,
}
BRAILLE_BASE = 0x2800

# Cells to pixels for each mode: (px_per_col, px_per_row).
_MODE_DIMS = {"half": (1, 2), "quad": (2, 2), "braille": (2, 4)}

# Two colours in a quad cell closer than this (squared RGB dist) are "the same".
_SPLIT_THRESHOLD = 48 * 48


def _dist2(a: RGB, b: RGB) -> int:
    """Squared RGB distance — cheap perceptual-ish nearness for colour splits."""
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _avg(colors: Sequence[RGB]) -> RGB:
    """Mean of a list of RGB triples (black if empty)."""
    n = len(colors)
    if n == 0:
        return (0, 0, 0)
    r = g = b = 0
    for c in colors:
        r += c[0]; g += c[1]; b += c[2]
    return (r // n, g // n, b // n)


# ==========================================================================
# SubcellRaster — the off-screen pixel buffer
# ==========================================================================
class SubcellRaster:
    """An off-screen pixel buffer at sub-cell resolution for one ``cols x rows``
    region, resolvable to Canvas cells via a mode-specific glyph mapping.

    The buffer is ``pw x ph`` *square* pixels where ``pw = cols * px_per_col``
    and ``ph = rows * px_per_row`` for the chosen mode. Each pixel is either a
    lit RGB colour or ``None`` (transparent — the cell keeps its Canvas value
    there). Draw with :meth:`set_pixel`/:meth:`line`/:meth:`disc`, then
    :meth:`to_canvas` or :meth:`blit_into` to resolve pixels to glyphs+colours.

    Because a pixel is square, all geometry (circles, isotropic distance) uses a
    plain Euclidean metric — the ASPECT=2 correction is already baked into the
    subdivision (2x taller cell split into 2 or 4 rows of pixels).
    """

    def __init__(self, cols: int, rows: int, mode: str = "half"):
        if mode not in _MODE_DIMS:
            raise ValueError(f"unknown mode {mode!r}; want one of {sorted(_MODE_DIMS)}")
        self.cols = max(0, int(cols))
        self.rows = max(0, int(rows))
        self.mode = mode
        self.pxc, self.pxr = _MODE_DIMS[mode]
        self.pw = self.cols * self.pxc
        self.ph = self.rows * self.pxr
        # None = transparent pixel; RGB tuple = lit.
        self.px: List[List[Optional[RGB]]] = [
            [None] * self.pw for _ in range(self.ph)
        ]

    # -- pixel primitives --------------------------------------------------
    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.pw and 0 <= y < self.ph

    def set_pixel(self, px: int, py: int, rgb: Optional[RGB]) -> None:
        """Light (or clear, if ``rgb is None``) one pixel. Clipped if OOB."""
        x, y = int(px), int(py)
        if 0 <= x < self.pw and 0 <= y < self.ph:
            self.px[y][x] = None if rgb is None else parse_color(rgb)

    def get_pixel(self, px: int, py: int) -> Optional[RGB]:
        if 0 <= px < self.pw and 0 <= py < self.ph:
            return self.px[py][px]
        return None

    def fill(self, rgb: Optional[RGB]) -> None:
        """Set every pixel to *rgb* (or clear all with ``None``)."""
        c = None if rgb is None else parse_color(rgb)
        for row in self.px:
            for x in range(self.pw):
                row[x] = c

    def fill_rect(self, x0: int, y0: int, w: int, h: int, rgb: Optional[RGB]) -> None:
        c = None if rgb is None else parse_color(rgb)
        for y in range(int(y0), int(y0) + int(h)):
            if 0 <= y < self.ph:
                row = self.px[y]
                for x in range(int(x0), int(x0) + int(w)):
                    if 0 <= x < self.pw:
                        row[x] = c

    def line(self, x0: int, y0: int, x1: int, y1: int, rgb: RGB) -> None:
        """Bresenham line from (x0,y0) to (x1,y1) in pixel space."""
        c = parse_color(rgb)
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.set_pixel(x0, y0, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(self, cx: float, cy: float, r: float, rgb: RGB) -> None:
        """Midpoint circle outline (radius in square pixels)."""
        c = parse_color(rgb)
        x = int(round(r))
        y = 0
        err = 1 - x
        cxi, cyi = int(round(cx)), int(round(cy))
        while x >= y:
            for sx, sy in ((x, y), (y, x), (-x, y), (-y, x),
                           (-x, -y), (-y, -x), (x, -y), (y, -x)):
                self.set_pixel(cxi + sx, cyi + sy, c)
            y += 1
            if err < 0:
                err += 2 * y + 1
            else:
                x -= 1
                err += 2 * (y - x) + 1

    def disc(self, cx: float, cy: float, r: float, rgb: RGB) -> None:
        """Filled disc (radius in square pixels). Euclidean => round on screen."""
        c = parse_color(rgb)
        r2 = r * r
        y0 = int(cy - r) - 1
        y1 = int(cy + r) + 1
        x0 = int(cx - r) - 1
        x1 = int(cx + r) + 1
        for py in range(y0, y1 + 1):
            if not (0 <= py < self.ph):
                continue
            dy = py - cy
            for px in range(x0, x1 + 1):
                if not (0 <= px < self.pw):
                    continue
                dx = px - cx
                if dx * dx + dy * dy <= r2:
                    self.px[py][px] = c

    # -- resolve one cell's pixels -> (glyph, fg, bg) ----------------------
    def _cell_pixels(self, cx: int, cy: int) -> List[List[Optional[RGB]]]:
        """The ``pxr x pxc`` block of pixels backing Canvas cell (cx, cy)."""
        bx, by = cx * self.pxc, cy * self.pxr
        return [[self.px[by + j][bx + i] for i in range(self.pxc)]
                for j in range(self.pxr)]

    def _resolve_half(self, block) -> Tuple[Optional[str], Optional[RGB], Optional[RGB]]:
        """1x2 pixels -> ▀/▄/█/space. fg=top px, bg=bottom px (RENDERING-MODEL §2)."""
        top = block[0][0]
        bot = block[1][0]
        if top is None and bot is None:
            return (None, None, None)          # transparent: leave the cell
        if top is not None and bot is not None:
            if top == bot:
                return (HALF_FULL, top, None)
            return (HALF_TOP, top, bot)        # upper block: fg top, bg bottom
        if top is not None:
            return (HALF_TOP, top, None)       # only top lit
        return (HALF_BOT, bot, None)           # only bottom lit

    def _resolve_quad(self, block) -> Tuple[Optional[str], Optional[RGB], Optional[RGB]]:
        """2x2 pixels -> quadrant glyph. Two-colour majority split: lit pixels are
        clustered into (up to) two colours; the larger cluster is fg, the glyph's
        mask marks fg pixels, the minority cluster becomes bg."""
        flat = [block[0][0], block[0][1], block[1][0], block[1][1]]  # TL,TR,BL,BR
        lit = [(i, c) for i, c in enumerate(flat) if c is not None]
        if not lit:
            return (None, None, None)
        colors = [c for _, c in lit]
        # Pick the two most separated colours as cluster seeds.
        seed_a = colors[0]
        seed_b = max(colors, key=lambda c: _dist2(c, seed_a))
        if _dist2(seed_a, seed_b) <= _SPLIT_THRESHOLD:
            # Effectively one colour: mask = lit pixels, single fg, no bg.
            mask = 0
            for i, _ in lit:
                mask |= 1 << i
            return (QUAD_GLYPHS[mask], _avg(colors), None)
        # Two-colour split: assign each lit pixel to nearest seed.
        grp_a: List[RGB] = []
        grp_b: List[RGB] = []
        mask = 0
        for i, c in lit:
            if _dist2(c, seed_a) <= _dist2(c, seed_b):
                grp_a.append(c)
                mask |= 1 << i         # group A = fg pixels
            else:
                grp_b.append(c)
        # Majority colour is fg (its mask bits set); minority fills bg.
        if len(grp_a) >= len(grp_b):
            return (QUAD_GLYPHS[mask], _avg(grp_a), _avg(grp_b))
        # Flip: make the bigger group fg by inverting the mask over lit pixels.
        lit_mask = 0
        for i, _ in lit:
            lit_mask |= 1 << i
        return (QUAD_GLYPHS[lit_mask ^ mask], _avg(grp_b), _avg(grp_a))

    def _resolve_braille(self, block) -> Tuple[Optional[str], Optional[RGB], Optional[RGB]]:
        """2x4 pixels -> U+2800 + 8-dot mask. fg = average of lit pixels, no bg."""
        mask = 0
        lit: List[RGB] = []
        for j in range(4):
            for i in range(2):
                c = block[j][i]
                if c is not None:
                    mask |= BRAILLE_BITS[(i, j)]
                    lit.append(c)
        if mask == 0:
            return (None, None, None)
        return (chr(BRAILLE_BASE + mask), _avg(lit), None)

    def resolve_cell(self, cx: int, cy: int) -> Tuple[Optional[str], Optional[RGB], Optional[RGB]]:
        """Resolve Canvas cell (cx, cy) to ``(glyph, fg, bg)``. ``glyph is None``
        means every backing pixel was transparent — leave the cell untouched."""
        block = self._cell_pixels(cx, cy)
        if self.mode == "half":
            return self._resolve_half(block)
        if self.mode == "quad":
            return self._resolve_quad(block)
        return self._resolve_braille(block)

    # -- write resolved pixels into a Canvas -------------------------------
    def blit_into(self, canvas: Canvas, ox: int = 0, oy: int = 0,
                  attrs: int = 0) -> None:
        """Resolve every cell and composite onto *canvas* at offset (ox, oy).

        Transparent cells (all backing pixels ``None``) are skipped so the
        raster overlays cleanly on whatever the Canvas already holds. Where a
        mode gives no bg (braille / single-colour cells) the Canvas bg is kept.
        """
        for cy in range(self.rows):
            for cx in range(self.cols):
                glyph, fg, bg = self.resolve_cell(cx, cy)
                if glyph is None:
                    continue
                tx, ty = ox + cx, oy + cy
                cell = canvas.cell(tx, ty)
                if cell is None:
                    continue
                cell.char = glyph
                cell.cont = False
                cell.attrs = attrs
                if fg is not None:
                    cell.fg = fg
                if bg is not None:
                    cell.bg = bg

    def to_canvas(self, bg: Optional[RGB] = None, attrs: int = 0) -> Canvas:
        """Resolve into a fresh ``cols x rows`` Canvas (transparent cells = *bg*)."""
        cv = Canvas(self.cols, self.rows, bg=bg)
        self.blit_into(cv, 0, 0, attrs)
        return cv


# ==========================================================================
# Image loading (optional PIL) — resize to pixel res, map into a raster
# ==========================================================================
def from_image(path: str, cols: int, rows: int, mode: str = "half",
               alpha_threshold: int = 128) -> "SubcellRaster":
    """Load an image into a :class:`SubcellRaster` at ``cols x rows`` cells.

    Requires Pillow (PIL). The image is resized to the mode's pixel resolution
    (``cols*px_per_col x rows*px_per_row``) and each pixel copied into the
    buffer; fully/mostly-transparent pixels (alpha < *alpha_threshold*) stay
    transparent so PNGs with cut-outs composite cleanly. Raises a clear
    ``RuntimeError`` (not an obscure ImportError) when PIL is missing.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError(
            "from_image needs Pillow (PIL): pip install pillow. "
            "Everything else in raster.py is pure stdlib."
        ) from exc

    r = SubcellRaster(cols, rows, mode)
    if r.pw == 0 or r.ph == 0:
        return r
    img = Image.open(path).convert("RGBA").resize((r.pw, r.ph))
    data = img.load()
    for py in range(r.ph):
        for px in range(r.pw):
            pr, pg, pb, pa = data[px, py]
            if pa >= alpha_threshold:
                r.px[py][px] = (pr, pg, pb)
    return r


# ==========================================================================
# Self-test — run as a module: python -m ui.raster
# ==========================================================================
def _selftest() -> None:
    def ok(name: str, cond: bool, detail: str = "") -> None:
        mark = "PASS" if cond else "FAIL"
        print(f"[{mark}] {name}" + (f"  {detail}" if detail else ""))
        if not cond:
            _selftest.failed = True  # type: ignore[attr-defined]

    # Windows consoles default to a legacy codepage (GBK/CP936) that can't encode
    # block/braille glyphs — force UTF-8 so the proof dump prints.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    _selftest.failed = False  # type: ignore[attr-defined]
    WHITE = (255, 255, 255)
    ASPECT = 2.0  # cell height : width (from field.py) — the roundness yardstick.

    def cell_bbox(lines):
        xs, ys = [], []
        for y, row in enumerate(lines):
            for x, ch in enumerate(row):
                if ch != " ":
                    xs.append(x); ys.append(y)
        return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)

    def px_bbox(r: SubcellRaster):
        xs, ys = [], []
        for y in range(r.ph):
            for x in range(r.pw):
                if r.px[y][x] is not None:
                    xs.append(x); ys.append(y)
        return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1) if xs else (0, 0)

    # --- half mode: filled disc uses block glyphs, and is a SQUARE in pixels-
    # Square pixel buffer (24 x 24) so a radius-10 disc fits without clipping.
    rh = SubcellRaster(24, 12, "half")  # pw=24, ph=24 square px
    cxp, cyp, rpx = rh.pw / 2 - 0.5, rh.ph / 2 - 0.5, 10.0
    rh.disc(cxp, cyp, rpx, WHITE)
    cvh = rh.to_canvas(bg=(0, 0, 0))
    lines_h = cvh.to_lines()
    used_blocks = any(ch in set("▀▄█") for row in lines_h for ch in row)
    ok("half: disc rasterizes to block glyphs", used_blocks)

    # THE roundness proof: the lit pixels form a square (w_px ≈ h_px). Square
    # pixels => a square pixel-region displays as a round disc on screen.
    pwid, phgt = px_bbox(rh)
    ok("half: disc is round (pixel bbox square)", abs(pwid - phgt) <= 1,
       f"px w={pwid} h={phgt}")

    # And in CELLS that square reads as w ≈ ASPECT*h (a 2:1 wide block), because
    # each half-mode cell is 2 px tall. That 2:1 cell block IS the round disc.
    hx0, hy0, hx1, hy1 = cell_bbox(lines_h)
    wc, hc = hx1 - hx0 + 1, hy1 - hy0 + 1
    ok("half: cells w≈ASPECT*h (round given cell 2:1)", abs(wc - ASPECT * hc) <= 2,
       f"w={wc} h={hc}  ASPECT*h={ASPECT * hc:.0f}")

    # --- braille mode: same disc, densest glyphs in U+2800 block ------------
    rb = SubcellRaster(12, 6, "braille")  # pw=24, ph=24 square px
    cxp2, cyp2, rpx2 = rb.pw / 2 - 0.5, rb.ph / 2 - 0.5, 10.0
    rb.disc(cxp2, cyp2, rpx2, WHITE)
    cvb = rb.to_canvas(bg=(0, 0, 0))
    lines_b = cvb.to_lines()
    braille_used = any(0x2800 <= ord(ch) <= 0x28FF and ch != chr(0x2800)
                       for row in lines_b for ch in row)
    ok("braille: disc rasterizes to U+2800 dot glyphs", braille_used)
    bwid, bhgt = px_bbox(rb)
    ok("braille: disc is round (pixel bbox square)", abs(bwid - bhgt) <= 1,
       f"px w={bwid} h={bhgt}")

    # --- braille mode: a diagonal line lights dots -------------------------
    rl = SubcellRaster(8, 4, "braille")
    rl.line(0, 0, rl.pw - 1, rl.ph - 1, WHITE)
    cvl = rl.to_canvas()
    diag_dots = sum(1 for row in cvl.to_lines() for ch in row
                    if 0x2801 <= ord(ch) <= 0x28FF)
    ok("braille: diagonal line lights dots", diag_dots >= 4, f"dot cells={diag_dots}")

    # --- half glyph mapping: fg=top px, bg=bottom px -----------------------
    rm = SubcellRaster(1, 1, "half")
    rm.set_pixel(0, 0, (10, 20, 30))     # top
    rm.set_pixel(0, 1, (200, 210, 220))  # bottom
    g, fg, bg = rm.resolve_cell(0, 0)
    ok("half: fg=top px, bg=bottom px", g == HALF_TOP and fg == (10, 20, 30)
       and bg == (200, 210, 220), f"glyph={g!r} fg={fg} bg={bg}")

    # --- quad glyph mapping: 2x2 mask -> quadrant glyph --------------------
    rq = SubcellRaster(1, 1, "quad")
    rq.set_pixel(0, 0, WHITE)  # TL only -> ▘
    gq, _, _ = rq.resolve_cell(0, 0)
    ok("quad: TL pixel -> ▘", gq == "▘", f"glyph={gq!r}")
    rq.set_pixel(1, 1, WHITE)  # + BR -> ▚ (TL+BR)
    gq2, _, _ = rq.resolve_cell(0, 0)
    ok("quad: TL+BR pixels -> ▚", gq2 == "▚", f"glyph={gq2!r}")

    # --- transparent cell is left untouched --------------------------------
    rt = SubcellRaster(2, 1, "half")
    rt.set_pixel(0, 0, WHITE)             # only cell 0 lit
    cvt = Canvas(2, 1, bg=(0, 0, 0))
    cvt.set(1, 0, "Z", fg=(1, 2, 3))
    rt.blit_into(cvt, 0, 0)
    ok("blit: transparent cell preserved", cvt.cell(1, 0).char == "Z",
       f"char={cvt.cell(1, 0).char!r}")

    # --- ascii dump: SHOW the round disc (proof, not a square) -------------
    print("\n  half-mode disc (11x11 cells, from an 11x22 square-pixel buffer):")
    for row in lines_h:
        print("    " + row.rstrip())
    print("\n  braille-mode disc (same geometry, 2x4 px/cell):")
    for row in lines_b:
        print("    " + row.rstrip())

    print()
    if getattr(_selftest, "failed"):
        print("SELF-TEST FAILED")
        sys.exit(1)
    print("SELF-TEST OK")


if __name__ == "__main__":
    _selftest()
