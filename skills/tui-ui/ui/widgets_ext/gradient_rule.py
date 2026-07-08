"""gradient_rule.py — a SOLID horizontal rule filled with a truecolor gradient.

WHY
---
The plain :class:`~ui.widgets.Rule` draws one flat color. Real product chrome
(the terminal ``/effort``-style divider, section headers, brand bars) wants a rule
whose color *sweeps* across its width — an indigo→violet→lavender wash on a
single unbroken ``─`` line. Codex botched this by falling back to a gray dashed
``--------`` rule; the fix is a genuinely SOLID line (U+2500) whose EVERY CELL
gets its own interpolated color, so the seam reads as one smooth bar, not a
row of dashes.

This widget is the reusable primitive for that: give it a list of color stops
and it lays a solid glyph across the region, sampling the multi-stop gradient
per cell via :func:`ui.core.gradient`. Truecolor, wide-char-safe (the fill glyph
is width-1 by contract), drop-in for any Box/VStack.

Params
------
* ``stops``   : sequence of color specs (``'#RRGGBB'`` or ``(r,g,b)``), >=1.
                The gradient runs left→right evenly across all stops.
* ``char``    : the fill glyph (default solid ``─``). Must be a 1-cell glyph.
* ``width``   : optional fixed cell width; otherwise fills the region handed down.
* ``attrs``   : optional text attrs (e.g. ``core.BOLD``); default 0 (full-bright).
* ``vertical``: if True, sweep top→bottom over the region height instead.
"""
from __future__ import annotations

from typing import Optional, Sequence

from .. import core
from ..core import Canvas, parse_color
from ..registry import register
from ..widgets import Widget

# The measured violet sweep from the /effort main rule (indigo → violet → lilac).
EFFORT_VIOLET_STOPS = ("#4C5BD4", "#7C5CE0", "#A78BFA")


@register
class GradientRule(Widget):
    """A solid horizontal (or vertical) rule with a per-cell multi-stop gradient."""
    key = "gradient_rule"
    summary = "Solid rule filled with a per-cell truecolor gradient"

    def __init__(self, stops: Sequence = EFFORT_VIOLET_STOPS, *, char: str = "─",
                 width: Optional[int] = None, attrs: int = 0,
                 vertical: bool = False, theme=None):
        super().__init__(theme)
        self.stops = tuple(parse_color(s) for s in stops) or (self.theme.accent,)
        self.char = char[:1] if char else "─"
        self.width = width          # honored by parent stacks when set
        self.attrs = attrs
        self.vertical = vertical

    # -- gradient sampling -------------------------------------------------
    def color_at(self, i: int, n: int) -> core.RGB:
        """RGB for cell *i* of *n* along the sweep (public: callers can reuse it)."""
        t = 0.0 if n <= 1 else i / (n - 1)
        return core.gradient(self.stops, t)

    def measure(self, avail_w, avail_h):
        if self.vertical:
            return (1, avail_h if self.width is None else self.width)
        return (self.width or max(2, avail_w), 1)

    def render(self, region_w, region_h):
        cv = Canvas(region_w, max(1, region_h), bg=self.theme.bg)
        if self.vertical:
            n = cv.h
            for y in range(n):
                cv.set(0, y, self.char, fg=self.color_at(y, n),
                       bg=self.theme.bg, attrs=self.attrs)
            return cv
        n = region_w
        for x in range(n):
            cv.set(x, 0, self.char, fg=self.color_at(x, n),
                   bg=self.theme.bg, attrs=self.attrs)
        return cv

    @classmethod
    def sample(cls, theme):
        # A vivid three-stop violet bar reads clearly in the gallery/demo.
        return cls(EFFORT_VIOLET_STOPS, theme=theme)
