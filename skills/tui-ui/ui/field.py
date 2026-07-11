"""field.py — CellField: the shader-field engine (primitive #1).

Everything renderable is a pure function of a cell::

    S(x, y, t) -> Sample(glyph, fg, bg, alpha)

ripple / glow / gradient / plasma are not bespoke widgets — they are different
``S``. The engine samples every cell, alpha-composites the result onto the
Canvas, and lets fields compose *algebraically* (``Over``/``Add``/``Mask``/
``Translate``). See references/RENDERING-MODEL.md §1.

THE load-bearing geometric fact: a terminal cell is ~2x taller than wide, so
``ASPECT = 2.0``. Any isotropic ("round", "equidistant") metric MUST scale y by
ASPECT or a circle renders as a vertical column. This is the aspect-correction
law (the ``((row-2)*2)^2`` distance term) in the measured ripple.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from .core import RGB, Canvas, clamp01, gradient, lerp_color, parse_color

# ==========================================================================
# Geometry (the one true metric — every isotropic field routes through this)
# ==========================================================================
ASPECT = 2.0  # cell height : width. y is stretched by this so round reads round.


def dist(x: float, y: float, ox: float, oy: float) -> float:
    """Aspect-corrected distance from (ox,oy) to (x,y). y is scaled by ASPECT."""
    dx = x - ox
    dy = (y - oy) * ASPECT
    return math.sqrt(dx * dx + dy * dy)


def angle(x: float, y: float, ox: float, oy: float) -> float:
    """Aspect-corrected angle of (x,y) about (ox,oy), radians. y scaled by ASPECT."""
    return math.atan2((y - oy) * ASPECT, x - ox)


# ==========================================================================
# Sample + CellField ABC
# ==========================================================================
@dataclass
class Sample:
    """What a field returns for one cell.

    * ``glyph``  : the character to write, or ``None`` = "don't touch the glyph,
                   only the background".
    * ``fg``     : foreground RGB to overwrite with, or ``None`` = leave fg.
    * ``bg``     : background RGB to composite, or ``None`` = no bg contribution.
    * ``alpha``  : blend weight in ``0..1``. 0 = fully transparent (cell untouched).
    """
    glyph: Optional[str] = None
    fg: Optional[RGB] = None
    bg: Optional[RGB] = None
    alpha: float = 0.0


# The universal "nothing here" sample — leave the cell exactly as it is.
EMPTY = Sample(None, None, None, 0.0)


class CellField(ABC):
    """A pure shader field. Subclass and implement :meth:`sample`.

    ``sample(x, y, t)`` is the whole contract — a fragment shader over the cell
    grid. :meth:`render_into` is the *only* place a field mutates a Canvas: it
    samples every cell in a region and composites the result (alpha-over on bg;
    glyph/fg overwrite when the sample provides them). Combinators subclass this
    too, so composed fields are still just a ``sample``.
    """

    @abstractmethod
    def sample(self, x: int, y: int, t: float = 0.0) -> Sample:
        """Return the :class:`Sample` for cell (x, y) at time phase ``t``."""
        raise NotImplementedError

    def render_into(self, canvas: Canvas, ox: int = 0, oy: int = 0,
                    w: Optional[int] = None, h: Optional[int] = None,
                    t: float = 0.0) -> None:
        """Sample every cell of the region and composite onto *canvas*.

        Region is ``w x h`` cells anchored at ``(ox, oy)``; defaults fill the rest
        of the canvas. Field-local coords are ``(0..w, 0..h)`` — the field never
        needs to know where it lives, so ``Translate`` and layout stay orthogonal.

        Compositing rule (the one place cells get written):
          * ``alpha <= 0`` → cell left untouched.
          * ``bg`` provided → alpha-over onto the cell's existing bg.
          * ``glyph`` provided → overwrites the char (and fg, if the sample gives
            one) at full weight; ``glyph is None`` means bg-only, glyph kept.
        """
        w = canvas.w - ox if w is None else w
        h = canvas.h - oy if h is None else h
        for yy in range(h):
            for xx in range(w):
                tx, ty = ox + xx, oy + yy
                cell = canvas.cell(tx, ty)
                if cell is None:
                    continue
                s = self.sample(xx, yy, t)
                a = clamp01(s.alpha)
                if a <= 0.0:
                    continue
                if s.bg is not None:
                    base = cell.bg if cell.bg is not None else s.bg
                    cell.bg = lerp_color(base, s.bg, a)
                if s.glyph is not None:
                    cell.char = s.glyph
                    cell.cont = False
                    if s.fg is not None:
                        cell.fg = s.fg
                elif s.fg is not None:
                    cell.fg = s.fg

    def to_canvas(self, w: int, h: int, t: float = 0.0, bg: Optional[RGB] = None) -> Canvas:
        """Convenience: render this field onto a fresh ``w x h`` Canvas."""
        cv = Canvas(w, h, bg=bg)
        self.render_into(cv, 0, 0, w, h, t)
        return cv


# ==========================================================================
# Field vocabulary — each is just one ``sample``. Same shape, different S.
# ==========================================================================
class LinearGradient(CellField):
    """Color along one axis: ``bg = gradient(stops, x/(w-1))`` (axis='x' or 'y').

    ``span`` fixes the normalization length; else it's inferred lazily per-axis
    from the first render extent. alpha=1 (opaque bg wash).
    """

    def __init__(self, stops: Sequence[RGB], axis: str = "x", span: Optional[int] = None):
        self.stops = tuple(parse_color(c) for c in stops)
        self.axis = axis
        self.span = span

    def sample(self, x: int, y: int, t: float = 0.0) -> Sample:
        n = max(1, (self.span if self.span else 40) - 1)
        p = (y if self.axis == "y" else x) / n
        return Sample(bg=gradient(self.stops, clamp01(p)), alpha=1.0)


class RadialGlow(CellField):
    """Isotropic light bloom: ``i = 1-(d/R)^2`` (quadratic) clamp0, else gaussian.

    ``d`` is ASPECT-corrected so the bloom reads round, not column-striped.
    bg = ramp sampled at intensity; alpha = intensity (feathers to transparent).
    """

    def __init__(self, center: tuple[float, float], radius: float,
                 ramp: Sequence[RGB], falloff: str = "quadratic"):
        self.ox, self.oy = center
        self.radius = max(0.001, radius)
        self.ramp = tuple(parse_color(c) for c in ramp)
        self.falloff = falloff

    def intensity(self, x: float, y: float) -> float:
        d = dist(x, y, self.ox, self.oy) / self.radius
        if d >= 1.0:
            return 0.0
        return math.exp(-((d * 2.0) ** 2)) if self.falloff == "gaussian" else 1.0 - d * d

    def sample(self, x: int, y: int, t: float = 0.0) -> Sample:
        i = self.intensity(x, y)
        return Sample(bg=gradient(self.ramp, i), alpha=i) if i > 0.0 else EMPTY


# The measured violet ultracode-ripple palette: 8-step lerp of the two ends.
RIPPLE_LO: RGB = (62, 22, 118)
RIPPLE_HI: RGB = (140, 80, 240)
RIPPLE_PALETTE: tuple[RGB, ...] = tuple(
    lerp_color(RIPPLE_LO, RIPPLE_HI, i / 7) for i in range(8)
)
RIPPLE_WHITE: RGB = (255, 255, 255)


class Ripple(CellField):
    """A traveling cosine wave — the ripple primitive behind the effort selector.

    Distance ``d = dist(col, row, originCol, originRow)`` (aspect-corrected, the
    ``((row-2)*2)^2`` law). Beyond the wavefront the cell is untouched::

        if d > travel:            -> alpha 0 (untouched)
        r = ((d - band) % λ + λ) % λ    # band = phase if given, else travel
        a = (1 + cos(2π r / λ)) / 2
        level = round(a * (n-1))
        bg = palette[level], alpha 1

    ``band`` is the distance offset of the cosine bands. By default (``phase``
    ``None``) it equals ``travel`` — the coupled default, where the bands are locked to
    the wavefront and travel outward with it. Supplying ``phase`` decouples the two:
    the wavefront cutoff still uses ``travel`` (the disk keeps growing at its own
    rate) while the cosine bands drift by ``phase`` — so the front can expand at one
    speed while the ripple shimmers at another. This is a pure generalization: with
    ``phase=None`` the math is byte-identical to the coupled default form.

    In ``text_over`` mode a covered cell keeps its glyph and is forced to white fg
    so text stays legible riding on the wave (the covered-cell color = white).
    """

    def __init__(self, origin: tuple[float, float], wavelength: float = 20.0,
                 travel: float = 0.0, palette: Sequence[RGB] = RIPPLE_PALETTE,
                 text_over: bool = False, glyph: Optional[str] = None,
                 covered_fg: RGB = RIPPLE_WHITE, falloff_radius: Optional[float] = None,
                 phase: Optional[float] = None):
        self.ox, self.oy = origin
        # Clamp wavelength to a tiny positive so a degenerate 0 can't
        # ZeroDivisionError in level_at (mirrors RadialGlow's radius clamp).
        self.wl = max(1e-6, float(wavelength))
        self.travel = float(travel)
        # A non-empty palette is required (level_at indexes it); fall back to the
        # trough color rather than IndexError on an empty palette.
        self.palette = tuple(parse_color(c) for c in palette) or (RIPPLE_PALETTE[0],)
        self.text_over = text_over
        self.glyph = glyph
        self.covered_fg = covered_fg
        # Optional radial falloff: alpha fades 1->0 from origin out to
        # falloff_radius, so the bloom feathers into the background instead of a
        # hard-edged opaque block. None = the opaque default. A 0 (or negative)
        # radius is treated as "no falloff" so it can't divide by zero.
        self.falloff_radius = falloff_radius if (falloff_radius or 0) > 0 else None
        # Optional band phase: distance offset of the cosine bands, decoupled from
        # the wavefront. None = the coupled default (bands ride the front, so the
        # subtracted term is `travel`).
        self.phase = None if phase is None else float(phase)

    def level_at(self, x: float, y: float) -> Optional[int]:
        """The palette index covering (x,y), or ``None`` if past the wavefront."""
        d = dist(x, y, self.ox, self.oy)
        if d > self.travel:
            return None
        band = self.travel if self.phase is None else self.phase
        r = ((d - band) % self.wl + self.wl) % self.wl
        a = (1.0 + math.cos(2.0 * math.pi * r / self.wl)) / 2.0
        return min(len(self.palette) - 1, round(a * (len(self.palette) - 1)))

    def sample(self, x: int, y: int, t: float = 0.0) -> Sample:
        level = self.level_at(x, y)
        if level is None:
            return EMPTY  # d > travel: cell untouched
        bg = self.palette[level]
        alpha = 1.0
        if self.falloff_radius is not None:
            d = dist(x, y, self.ox, self.oy)
            # smooth 1->0 over the radius (quadratic ease); past radius = 0
            f = 1.0 - (d / self.falloff_radius)
            alpha = max(0.0, f * f)
            if alpha <= 0.0:
                return EMPTY
        if self.text_over:
            # text stays legible only where the glow is strong enough
            fg = self.covered_fg if alpha > 0.4 else None
            return Sample(glyph=self.glyph, fg=fg, bg=bg, alpha=alpha)
        return Sample(glyph=self.glyph, bg=bg, alpha=alpha)


class Plasma(CellField):
    """Sum-of-sines plasma → ramp color. Proof the engine generalizes past round.

    ``v = (sin(x·fx) + sin(y·fy·ASPECT) + sin((x+y+t·k))) / 3`` remapped to 0..1
    then sampled through ``ramp``. ``t`` scrolls it. alpha=1 (opaque wash).
    """

    def __init__(self, ramp: Sequence[RGB], fx: float = 0.30, fy: float = 0.20,
                 speed: float = 6.0):
        self.ramp = tuple(parse_color(c) for c in ramp)
        self.fx, self.fy, self.speed = fx, fy, speed

    def sample(self, x: int, y: int, t: float = 0.0) -> Sample:
        v = (math.sin(x * self.fx)
             + math.sin(y * self.fy * ASPECT)
             + math.sin((x + y + t * self.speed) * 0.15)) / 3.0
        return Sample(bg=gradient(self.ramp, (v + 1.0) / 2.0), alpha=1.0)


# ==========================================================================
# Compositor combinators — fields compose algebraically (each is a CellField)
# ==========================================================================
class Over(CellField):
    """Alpha-over: ``a`` composited on top of ``b`` (Porter-Duff source-over).

    Where ``a`` is opaque it wins; where it's transparent ``b`` shows through;
    partial alphas blend. Glyph/fg follow ``a`` when it provides them, else ``b``.
    """

    def __init__(self, a: CellField, b: CellField):
        self.a, self.b = a, b

    def sample(self, x: int, y: int, t: float = 0.0) -> Sample:
        sa = self.a.sample(x, y, t)
        sb = self.b.sample(x, y, t)
        aa = clamp01(sa.alpha)
        ab = clamp01(sb.alpha)
        out = aa + ab * (1.0 - aa)  # combined coverage
        if out <= 0.0:
            return EMPTY
        # Blend bg by source-over of the two premultiplied contributions.
        if sa.bg is not None and sb.bg is not None:
            bg = lerp_color(sb.bg, sa.bg, aa)
        else:
            bg = sa.bg if sa.bg is not None else sb.bg
        glyph = sa.glyph if sa.glyph is not None else sb.glyph
        fg = sa.fg if sa.fg is not None else sb.fg
        return Sample(glyph=glyph, fg=fg, bg=bg, alpha=out)


class Add(CellField):
    """Additive light: bg channels summed & clamped, alpha = max. For glows."""

    def __init__(self, a: CellField, b: CellField):
        self.a, self.b = a, b

    def sample(self, x: int, y: int, t: float = 0.0) -> Sample:
        sa = self.a.sample(x, y, t)
        sb = self.b.sample(x, y, t)
        if sa.alpha <= 0.0 and sb.alpha <= 0.0:
            return EMPTY
        ca = sa.bg or (0, 0, 0)
        cb = sb.bg or (0, 0, 0)
        bg = (min(255, ca[0] + cb[0]), min(255, ca[1] + cb[1]), min(255, ca[2] + cb[2]))
        glyph = sa.glyph if sa.glyph is not None else sb.glyph
        fg = sa.fg if sa.fg is not None else sb.fg
        return Sample(glyph=glyph, fg=fg, bg=bg, alpha=max(sa.alpha, sb.alpha))


class Mask(CellField):
    """Gate a field through ``mask_fn(x,y,t)->0..1``: multiplies the sample alpha."""

    def __init__(self, field: CellField, mask_fn: Callable[[int, int, float], float]):
        self.field, self.mask_fn = field, mask_fn

    def sample(self, x: int, y: int, t: float = 0.0) -> Sample:
        s = self.field.sample(x, y, t)
        m = clamp01(self.mask_fn(x, y, t))
        if m <= 0.0 or s.alpha <= 0.0:
            return EMPTY
        return Sample(glyph=s.glyph, fg=s.fg, bg=s.bg, alpha=clamp01(s.alpha * m))


class Translate(CellField):
    """Spatial shift: samples ``field`` at ``(x-dx, y-dy)`` — moves the field."""

    def __init__(self, field: CellField, dx: float, dy: float):
        self.field, self.dx, self.dy = field, dx, dy

    def sample(self, x: int, y: int, t: float = 0.0) -> Sample:
        return self.field.sample(int(round(x - self.dx)), int(round(y - self.dy)), t)


# ==========================================================================
# Self-test — run as a module: python -m ui.field
# ==========================================================================
def _selftest() -> None:
    import sys

    def ok(name: str, cond: bool, detail: str = "") -> None:
        mark = "PASS" if cond else "FAIL"
        print(f"[{mark}] {name}" + (f"  {detail}" if detail else ""))
        if not cond:
            _selftest.failed = True  # type: ignore[attr-defined]

    _selftest.failed = False  # type: ignore[attr-defined]

    # --- RadialGlow: center brighter than edge -----------------------------
    glow = RadialGlow(center=(10, 10), radius=8.0, ramp=RIPPLE_PALETTE)
    ic = glow.intensity(10, 10)
    ie = glow.intensity(17, 10)
    ok("radial: center brighter than edge", ic > ie, f"center={ic:.4f} edge={ie:.4f}")

    # --- RadialGlow: isotropy — round, not column-striped ------------------
    # A step of 1 cell in +x vs a step in +y must be symmetric AFTER aspect
    # correction. ASPECT=2 means 1 cell in y == 2 cells in x geometrically, so
    # intensity(+2x) should equal intensity(+1y).
    ix2 = glow.intensity(12, 10)   # +2 cells in x
    iy1 = glow.intensity(10, 11)   # +1 cell  in y (==2 x-units after ASPECT)
    ok("radial: isotropic (round, not striped)", abs(ix2 - iy1) < 1e-9,
       f"i(+2x)={ix2:.6f} i(+1y)={iy1:.6f} delta={abs(ix2 - iy1):.2e}")
    # And a naive no-aspect comparison would be lopsided — prove the correction
    # is load-bearing: +1x != +1y (that asymmetry is the round-ness).
    ix1 = glow.intensity(11, 10)
    ok("radial: aspect actually applied", abs(ix1 - glow.intensity(10, 11)) > 1e-6,
       f"i(+1x)={ix1:.6f} i(+1y)={glow.intensity(10, 11):.6f}")

    # --- Ripple: d>travel untouched (alpha 0) ------------------------------
    rip = Ripple(origin=(0, 2), wavelength=20.0, travel=10.0)
    # A far cell well beyond travel must be None (untouched).
    far = rip.level_at(40, 2)
    ok("ripple: d>travel untouched", far is None, f"level_at(40,2)={far}")
    # Verify via a real render: those cells keep their original bg.
    cv = Canvas(50, 5, bg=(0, 0, 0))
    cv.set(40, 2, "X", bg=(1, 2, 3))
    rip.render_into(cv, 0, 0, 50, 5, 0.0)
    untouched = cv.cell(40, 2).bg == (1, 2, 3)
    ok("ripple: untouched cell bg preserved on render", untouched,
       f"bg={cv.cell(40, 2).bg}")

    # --- Ripple: wave expands (covered set changes with travel) ------------
    def covered_set(travel: float) -> set:
        r = Ripple(origin=(0, 2), wavelength=20.0, travel=travel)
        return {(x, y) for y in range(5) for x in range(50)
                if r.level_at(x, y) is not None}
    c10 = covered_set(10.0)
    c25 = covered_set(25.0)
    ok("ripple: wave expands with travel", c10 != c25 and c25 > c10,
       f"|covered@10|={len(c10)} |covered@25|={len(c25)}")

    # --- Ripple text_over: covered cell keeps glyph + white fg -------------
    cv2 = Canvas(50, 5, bg=(0, 0, 0))
    cv2.set(3, 2, "E", fg=(30, 30, 30))
    rip_t = Ripple(origin=(0, 2), wavelength=20.0, travel=30.0, text_over=True)
    rip_t.render_into(cv2, 0, 0, 50, 5, 0.0)
    c = cv2.cell(3, 2)
    ok("ripple: text_over keeps glyph + white fg",
       c.char == "E" and c.fg == RIPPLE_WHITE, f"char={c.char!r} fg={c.fg}")

    # --- Ripple palette: exact measured 8-step lerp ------------------------
    ok("ripple: palette endpoints match the measured original",
       RIPPLE_PALETTE[0] == RIPPLE_LO and RIPPLE_PALETTE[-1] == RIPPLE_HI,
       f"{RIPPLE_PALETTE[0]}..{RIPPLE_PALETTE[-1]} n={len(RIPPLE_PALETTE)}")

    # --- Compositor: Over blends, Mask gates -------------------------------
    over = Over(RadialGlow((5, 5), 4.0, RIPPLE_PALETTE),
                LinearGradient([(0, 0, 0), (100, 100, 100)], "x", span=20))
    so = over.sample(5, 5, 0.0)
    ok("over: opaque top wins alpha", so.alpha >= 0.999, f"alpha={so.alpha:.4f}")
    masked = Mask(LinearGradient([(0, 0, 0), (255, 255, 255)], "x", span=20),
                  lambda x, y, t: 1.0 if x < 5 else 0.0)
    ok("mask: gate zeroes alpha outside", masked.sample(9, 0).alpha == 0.0
       and masked.sample(1, 0).alpha == 1.0)

    # --- Translate: shifts sample coords -----------------------------------
    base = RadialGlow((0, 0), 6.0, RIPPLE_PALETTE)
    tr = Translate(base, 5, 0)
    ok("translate: peak moves with dx",
       abs(tr.sample(5, 0).alpha - base.sample(0, 0).alpha) < 1e-9,
       f"tr(5,0)={tr.sample(5, 0).alpha:.4f} base(0,0)={base.sample(0, 0).alpha:.4f}")

    print()
    if getattr(_selftest, "failed"):
        print("SELF-TEST FAILED")
        sys.exit(1)
    print("SELF-TEST OK")


if __name__ == "__main__":
    _selftest()
