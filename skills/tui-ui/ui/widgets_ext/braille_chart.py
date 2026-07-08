"""braille_chart.py — a SMOOTH sub-cell line chart drawn in braille pixels.

WHY
---
Until now the catalog had NO chart/graph widget: ``progress``/``meter`` draw
blocky horizontal bars and ``banner`` draws glyph art, but nothing plots a data
*series* as a trend line. A per-cell plot is forever staircased — a cell is the
smallest thing a Canvas can address, so a line built from ``─``/``█`` jumps a
whole row at a time. The escape hatch is the engine's already-complete sub-cell
raster: braille (``U+2800``..``U+28FF``) packs **2×4 pixels per cell**, so an
``W×H`` chart has an ``W*2 × H*4`` pixel buffer — 8× the vertical resolution —
and a Bresenham line through it reads as one smooth curve, not a bar chart.

This is the literal realization of RENDERING-MODEL §2 (`平滑进度条/迷你图 (mini-
graphs)` route through :class:`~ui.raster.SubcellRaster`) and the knowledge note
[[sub-cell-resolution]]: render the series into a real pixel buffer, then
downsample each cell's 2×4 block to the best braille glyph + colour. No new
dependency — pure stdlib, composing the ``raster.line()`` primitive.

Contract
--------
Pure FRAME PRODUCER: :meth:`render` returns a Canvas of EXACTLY ``region_w`` ×
``region_h`` cells (every row exactly ``region_w`` display cells — the tmux-safe,
no-fr-drift invariant the smoke harness enforces). Never prints, sleeps, or
touches ANSI modes.

Params
------
* ``series``    : sequence of numbers to plot left→right. Empty / single-point /
                  all-equal series are handled gracefully (blank / dot / flat
                  mid-line) and never raise.
* ``width`` / ``height`` : target size in CELLS (honoured by parent stacks when
                  set; otherwise the widget fills the region handed down).
* ``y_range``   : explicit ``(ymin, ymax)`` for the vertical axis; ``None`` →
                  autoscale to ``min(series)``..``max(series)``.
* ``gradient``  : colour the line by its x-fraction via ``theme.color_at`` (the
                  theme's ``stops`` sweep); ``False`` → solid ``theme.accent``.
* ``line_color``: explicit RGB / ``'#RRGGBB'`` override (solid); wins over
                  ``gradient``.
"""
from __future__ import annotations

from typing import Optional, Sequence

from .. import core
from ..core import Canvas, parse_color
from ..raster import SubcellRaster
from ..registry import register
from ..widgets import Widget


@register
class BrailleChart(Widget):
    """A smooth line chart of a numeric series, rasterized in 2×4 braille pixels."""
    key = "braille_chart"
    summary = "Smooth sub-cell line chart of a data series (braille)"

    def __init__(self, series: Sequence[float] = (), *,
                 width: Optional[int] = None, height: Optional[int] = None,
                 y_range: Optional[tuple[float, float]] = None,
                 gradient: bool = True, line_color=None, theme=None):
        super().__init__(theme)
        self.series = [float(v) for v in series]
        self.width = width            # honoured by parent stacks when set
        self.height = height
        self.y_range = y_range
        self.gradient = gradient
        self.line_color = parse_color(line_color) if line_color is not None else None

    # -- scaling -----------------------------------------------------------
    def _y_bounds(self) -> tuple[float, float]:
        """(ymin, ymax) for the vertical axis; explicit range wins, else autoscale.

        A degenerate series (empty, single point, or all-equal) collapses to a
        zero-height span; we widen it by ±1 so the trend lands on the mid-line
        instead of dividing by zero."""
        if self.y_range is not None:
            lo, hi = float(self.y_range[0]), float(self.y_range[1])
        elif self.series:
            lo, hi = min(self.series), max(self.series)
        else:
            lo, hi = 0.0, 0.0
        if hi <= lo:
            lo, hi = lo - 1.0, hi + 1.0     # flat/degenerate → centered band
        return lo, hi

    def _color_for(self, x_frac: float) -> core.RGB:
        """Line colour at horizontal fraction *x_frac* in ``[0,1]``."""
        if self.line_color is not None:
            return self.line_color
        if self.gradient:
            return self.theme.color_at(x_frac)
        return self.theme.accent

    # -- rasterization (public: reusable / testable) -----------------------
    def rasterize(self, cols: int, rows: int) -> SubcellRaster:
        """Draw the series into a fresh braille :class:`SubcellRaster` (2×4 px/cell).

        x maps evenly across the ``cols*2`` pixel columns; y maps the value range
        onto the ``rows*4`` pixel rows (inverted — larger values sit higher). A
        single point lights one dot; two+ points connect via Bresenham segments so
        the trend reads smooth at sub-cell resolution."""
        r = SubcellRaster(cols, rows, mode="braille")
        if r.pw == 0 or r.ph == 0 or not self.series:
            return r
        lo, hi = self._y_bounds()
        span = hi - lo
        pw, ph = r.pw, r.ph
        n = len(self.series)

        def px(i: int) -> int:
            frac = 0.0 if n <= 1 else i / (n - 1)
            return int(round(frac * (pw - 1)))

        def py(v: float) -> int:
            # value → pixel row, inverted so high values are near the top (y=0).
            t = 0.5 if span <= 0 else (v - lo) / span
            t = core.clamp01(t)
            return int(round((1.0 - t) * (ph - 1)))

        if n == 1:
            r.set_pixel(px(0), py(self.series[0]), self._color_for(0.0))
            return r
        prev_x, prev_y = px(0), py(self.series[0])
        for i in range(1, n):
            cx, cy = px(i), py(self.series[i])
            # colour each segment by its right endpoint's x-fraction.
            r.line(prev_x, prev_y, cx, cy, self._color_for(i / (n - 1)))
            prev_x, prev_y = cx, cy
        return r

    # -- widget protocol ---------------------------------------------------
    def measure(self, avail_w, avail_h):
        return (self.width or max(2, avail_w), self.height or max(1, avail_h))

    def render(self, region_w, region_h):
        cols = self.width or region_w
        rows = self.height or region_h
        cv = Canvas(region_w, max(1, region_h), bg=self.theme.bg)
        cols = min(cols, cv.w)
        rows = min(rows, cv.h)
        if cols > 0 and rows > 0:
            self.rasterize(cols, rows).blit_into(cv, 0, 0)
        return cv

    @classmethod
    def sample(cls, theme):
        # A sine wave reads unmistakably as a smooth curve in the gallery/demo.
        import math
        series = [math.sin(i / 6.0) for i in range(64)]
        return cls(series, theme=theme)

