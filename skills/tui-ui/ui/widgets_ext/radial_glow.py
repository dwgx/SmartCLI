"""radial_glow.py — a LOCAL, ROUNDED, PULSING radial glow field.

WHY
---
The ``/effort`` ultracode effect is a soft violet light *bloom* centered on the
``ultracode`` label: brightest at a core, feathering out to nothing with rounded
edges, breathing in and out over time — and the label text stays crisp on top.

Codex got this wrong twice: it painted a full-width, hard-edged, opaque
rectangular column plasma that (a) had sharp borders instead of rounded feather,
and (b) overwrote/washed out the text sitting on it. Both failures come from the
same mistake — treating the glow as *foreground blocks* instead of a *background
light field*.

This widget fixes both:
  * Intensity is ``f(distance-from-center)`` with a smooth falloff (quadratic
    ``1-(d/R)^2`` or gaussian), so the core is bright and edges feather to zero —
    ROUNDED, never a hard rectangle. Distance uses an elliptical/superellipse
    metric with a cell-aspect correction (terminal cells are ~2x taller than
    wide) so the bloom reads circular, and a shaping exponent lets you go from a
    soft ellipse toward a rounded-corner rectangle without ever getting hard
    corners.
  * It composites as BACKGROUND only. :meth:`paint_bg` sets each covered cell's
    ``.bg`` and leaves the ``char``/``fg``/``attrs`` intact, so you draw your
    text first and the glow slides in behind it — text stays fully legible.
  * ``t`` (an animation phase in ``[0,1)``) drives a sine "breathing" pulse of the
    radius between ``pulse_min``..``pulse_max`` and an optional center drift, so a
    caller just advances ``t`` each frame to animate. The bright center stays
    locked over the target.

Params
------
* ``width`` / ``height`` : the rectangular region the field is sampled over.
* ``center``   : ``(cx, cy)`` fractional cell coords of the core (default: middle).
* ``radius``   : base falloff radius in *horizontal cells* (the ellipse semi-axis);
                 ``None`` → derived from region. Vertical radius = radius/aspect.
* ``aspect``   : cell height:width ratio for round-looking bloom (default 2.0).
* ``colors``   : ramp stops sampled edge(intensity 0)→core(intensity 1). Defaults
                 to the measured deep-purple→lavender ultracode ramp.
* ``inner_color`` / ``outer_color`` : convenience 2-stop ramp (overrides ``colors``).
* ``base_bg``  : the panel bg the glow dissolves into (default: theme bg).
* ``falloff``  : ``"quadratic"`` (``1-(d/R)^2``) or ``"gaussian"``.
* ``exponent`` : superellipse power for the distance metric (2 = ellipse/rounded;
                 higher → squarer body but corners stay rounded/feathered).
* ``t``        : animation phase in ``[0,1)`` (breathing + drift). Default 0.
* ``pulse_min`` / ``pulse_max`` : radius scale at the trough/peak of the breath.
* ``drift``    : ``(dx, dy)`` max center wobble in cells over the pulse.
* ``gamma``    : alpha shaping; alpha = ``intensity ** gamma`` (default 1.0).
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from .. import core
from ..core import Canvas, parse_color
from ..registry import register
from ..widgets import Widget

# Measured ultracode ramp, edge (transparent-ish deep purple) → near-white core.
ULTRACODE_RAMP = ("#4A1E8C", "#5A2EA6", "#7C4DD6", "#8B5CF6", "#B98CF0", "#C7A8FF")


@register
class RadialGlow(Widget):
    """A localized rounded radial glow, composited as a background light field."""
    key = "radial_glow"
    summary = "Localized rounded/pulsing radial glow (background light field)"

    def __init__(self, width: Optional[int] = None, height: Optional[int] = None, *,
                 center=None, radius: Optional[float] = None, aspect: float = 2.0,
                 colors: Sequence = ULTRACODE_RAMP, inner_color=None, outer_color=None,
                 base_bg=None, falloff: str = "quadratic", exponent: float = 2.0,
                 t: float = 0.0, pulse_min: float = 0.72, pulse_max: float = 1.0,
                 drift=(0.0, 0.0), gamma: float = 1.0, theme=None):
        super().__init__(theme)
        self.width = width
        self.height = height
        self.center = center
        self.radius = radius
        self.aspect = max(0.1, aspect)
        if inner_color is not None or outer_color is not None:
            oc = parse_color(outer_color) if outer_color is not None else parse_color(ULTRACODE_RAMP[0])
            ic = parse_color(inner_color) if inner_color is not None else parse_color(ULTRACODE_RAMP[-1])
            self.ramp = (oc, ic)
        else:
            self.ramp = tuple(parse_color(c) for c in colors)
        self.base_bg = parse_color(base_bg) if base_bg is not None else self.theme.bg
        self.falloff = falloff
        self.exponent = max(1.0, exponent)
        self.t = t
        self.pulse_min = pulse_min
        self.pulse_max = pulse_max
        self.drift = drift
        self.gamma = max(0.01, gamma)

    # -- animation-resolved geometry --------------------------------------
    def _pulse_scale(self) -> float:
        # Sine breathing: t=0 → trough (pulse_min), eases up to peak and back.
        s = 0.5 - 0.5 * math.cos(2.0 * math.pi * (self.t % 1.0))  # 0..1..0
        return self.pulse_min + (self.pulse_max - self.pulse_min) * s

    def _resolved_center(self, w: int, h: int) -> tuple[float, float]:
        cx, cy = self.center if self.center is not None else ((w - 1) / 2.0, (h - 1) / 2.0)
        # A slow circular drift synced to the phase, capped by ``drift``.
        dx, dy = self.drift
        ang = 2.0 * math.pi * (self.t % 1.0)
        return (cx + dx * math.cos(ang), cy + dy * math.sin(ang))

    # -- intensity field (public: reusable / testable) --------------------
    def intensity_at(self, x: float, y: float, w: int, h: int) -> float:
        """Glow intensity in ``[0,1]`` at cell (x, y): 1 at core, 0 past the edge."""
        cx, cy = self._resolved_center(w, h)
        rx = self.radius if self.radius is not None else max(1.0, w / 2.0)
        rx *= self._pulse_scale()
        ry = max(0.5, rx / self.aspect)
        # Superellipse distance: |dx/rx|^p + |dy/ry|^p, rounded for p>=2.
        ndx = abs(x - cx) / max(0.001, rx)
        ndy = abs(y - cy) / max(0.001, ry)
        d = (ndx ** self.exponent + ndy ** self.exponent) ** (1.0 / self.exponent)
        if d >= 1.0:
            return 0.0
        if self.falloff == "gaussian":
            return math.exp(-((d * 2.0) ** 2))
        return 1.0 - d * d  # quadratic: 1-(d/R)^2

    def color_at(self, x: float, y: float, w: int, h: int) -> tuple[core.RGB, float]:
        """Return ``(glow_rgb, alpha)`` for a cell — alpha is the blend weight."""
        it = self.intensity_at(x, y, w, h)
        glow = core.gradient(self.ramp, it)
        return glow, it ** self.gamma

    def bg_at(self, x: float, y: float, w: int, h: int, under=None) -> Optional[core.RGB]:
        """Composited background RGB at a cell (glow alpha-blended over *under*)."""
        glow, alpha = self.color_at(x, y, w, h)
        if alpha <= 0.0:
            return under
        base = under if under is not None else self.base_bg
        return core.lerp_color(base, glow, alpha)

    # -- compositing --------------------------------------------------------
    def paint_bg(self, canvas: Canvas, ox: int = 0, oy: int = 0,
                 w: Optional[int] = None, h: Optional[int] = None) -> None:
        """Blend the glow into the BACKGROUND of an existing canvas region.

        Touches only each cell's ``.bg``; ``char``/``fg``/``attrs`` are preserved,
        so text drawn before OR after this call reads crisply on top of the glow.
        This is the "composite behind text" primitive the ultracode effect uses.
        """
        w = w if w is not None else (self.width or (canvas.w - ox))
        h = h if h is not None else (self.height or (canvas.h - oy))
        for yy in range(h):
            for xx in range(w):
                tx, ty = ox + xx, oy + yy
                cell = canvas.cell(tx, ty)
                if cell is None:
                    continue
                new_bg = self.bg_at(xx, yy, w, h, under=cell.bg or self.base_bg)
                if new_bg is not None:
                    cell.bg = new_bg

    def measure(self, avail_w, avail_h):
        return (self.width or avail_w, self.height or avail_h)

    def render(self, region_w, region_h):
        """Standalone render: a filled field of glow-bg cells (for demo/self-test)."""
        w = self.width or region_w
        h = self.height or region_h
        cv = Canvas(region_w, max(1, region_h), bg=self.base_bg)
        for yy in range(min(h, cv.h)):
            for xx in range(min(w, cv.w)):
                bg = self.bg_at(xx, yy, w, h, under=self.base_bg)
                cv.set(xx, yy, " ", bg=bg)
        return cv

    @classmethod
    def sample(cls, theme):
        # A tight bloom in a wide-ish region shows the rounded feathered falloff.
        return cls(40, 9, radius=14.0, base_bg=theme.bg, theme=theme)
