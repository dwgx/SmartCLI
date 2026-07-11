"""layout.py — flexbox/grid layout on a cell grid.

Containers compose boxes and widgets into a full page. The load-bearing part is
``fr`` distribution: never round each track independently (that gives total +/-1
drift). We use Rich's carry-remainder method (research §2a):

    size, remainder = divmod(portion * weight + remainder, 1)

so ``10`` cells split ``1fr 1fr 1fr`` -> ``[3, 3, 4]`` exactly, and cumulative
offsets never drift. Fixed/auto children are measured first and subtracted; the
remainder is shared among ``fr`` children by weight.

Containers implement the same ``measure(w,h)`` / ``render(w,h)`` protocol as boxes
and widgets, so they nest arbitrarily (a VStack of HStacks of Panels ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from . import core
from .box import Box, Fr, parse_dim
from .core import Canvas, parse_color


def resolve_tracks(total: int, specs: list, naturals: list[int],
                   gap: int = 0) -> list[int]:
    """Resolve a 1-D track layout to integer cell sizes summing to <= total.

    ``specs`` entries are int (fixed), Fr (flexible), a percent string like
    ``"33%"``, or 'auto'. (Percent strings are normalised by ``parse_dim``;
    pass the ``"33%"`` string form, not a raw ``('pct', p)`` tuple.)
    ``naturals`` supplies the auto/content size per track. ``gap`` cells sit
    between adjacent tracks. Uses carry-remainder so fr tracks tile exactly.
    """
    n = len(specs)
    if n == 0:
        return []
    gaps_total = gap * (n - 1)
    avail = max(0, total - gaps_total)

    sizes: list[Optional[int]] = [None] * n
    fr_weights: list[float] = [0.0] * n
    for i, spec in enumerate(specs):
        spec = parse_dim(spec)
        if isinstance(spec, Fr):
            fr_weights[i] = max(0.0, spec.value)
        elif isinstance(spec, int):
            sizes[i] = max(0, spec)
        elif isinstance(spec, tuple) and spec[0] == "pct":
            sizes[i] = max(0, round(avail * spec[1] / 100.0))
        else:  # auto
            sizes[i] = max(0, naturals[i])

    fixed = sum(s for s in sizes if s is not None)
    remaining = max(0, avail - fixed)
    total_weight = sum(fr_weights)

    if total_weight > 0:
        portion = Fraction(remaining) / Fraction(total_weight).limit_denominator()
        remainder = Fraction(0)
        for i in range(n):
            if fr_weights[i] > 0:
                raw = portion * Fraction(fr_weights[i]).limit_denominator() + remainder
                size, remainder = divmod(raw, 1)
                sizes[i] = int(size)
    else:
        sizes = [s or 0 for s in sizes]

    # If fixed/auto tracks overflow, shrink them proportionally to fit.
    resolved = [s or 0 for s in sizes]
    over = sum(resolved) - avail
    if over > 0:
        _shrink_to_fit(resolved, avail)
    return resolved


def _shrink_to_fit(sizes: list[int], avail: int) -> None:
    """Reduce sizes in place (largest-first) until they sum to <= avail."""
    while sum(sizes) > avail and any(s > 0 for s in sizes):
        i = max(range(len(sizes)), key=lambda k: sizes[k])
        sizes[i] -= 1


def _align_offset(outer: int, inner: int, align: str) -> int:
    if inner >= outer:
        return 0
    if align in ("center", "middle"):
        return (outer - inner) // 2
    if align in ("right", "bottom", "end"):
        return outer - inner
    return 0


# --------------------------------------------------------------------------
# Stacks
# --------------------------------------------------------------------------
@dataclass
class Stack:
    """Base for VStack/HStack. ``children`` are boxes/widgets/containers.

    Per-child main-axis size comes from the child's own ``width``/``height``
    (Box) or defaults to fr=1 for plain widgets. ``gap`` inserts blank cells
    between children. ``align``/``valign`` position the whole content block when
    it is smaller than the region on the cross axis.
    """
    children: list = field(default_factory=list)
    gap: int = 0
    bg: object = None
    align: str = "left"      # cross-axis for VStack / main-end handling
    valign: str = "top"
    horizontal: bool = False

    def _child_spec(self, child, axis: str):
        """Main-axis dimension spec for a child (int/Fr/'auto'/pct)."""
        dim = getattr(child, axis, None)
        if dim is None:
            return Fr(1.0)  # widgets with no explicit size flex to fill
        return dim

    def _child_natural(self, child, axis_idx: int, region) -> int:
        w, h = child.measure(region[0], region[1])
        return w if axis_idx == 0 else h

    def measure(self, avail_w: int, avail_h: int) -> tuple[int, int]:
        if not self.children:
            return (0, 0)
        cross_max = 0
        main_sum = 0
        for c in self.children:
            w, h = c.measure(avail_w, avail_h)
            if self.horizontal:
                main_sum += w
                cross_max = max(cross_max, h)
            else:
                main_sum += h
                cross_max = max(cross_max, w)
        main_sum += self.gap * (len(self.children) - 1)
        return (main_sum, cross_max) if self.horizontal else (cross_max, main_sum)

    def render(self, region_w: int, region_h: int) -> Canvas:
        bg = parse_color(self.bg)
        out = Canvas(region_w, region_h, fg=None, bg=bg)
        if not self.children:
            return out

        axis = "width" if self.horizontal else "height"
        axis_idx = 0 if self.horizontal else 1
        main_total = region_w if self.horizontal else region_h
        cross_total = region_h if self.horizontal else region_w

        specs = [self._child_spec(c, axis) for c in self.children]
        naturals = [self._child_natural(c, axis_idx, (region_w, region_h))
                    for c in self.children]
        sizes = resolve_tracks(main_total, specs, naturals, gap=self.gap)

        pos = 0
        for child, main_size in zip(self.children, sizes):
            if main_size <= 0:
                pos += self.gap
                continue
            if self.horizontal:
                cw, chh = main_size, cross_total
                cv = child.render(cw, chh)
                oy = _align_offset(chh, cv.h, self.valign)
                out.blit(cv, pos, oy)
            else:
                cw, chh = cross_total, main_size
                cv = child.render(cw, chh)
                ox = _align_offset(cw, cv.w, self.align)
                out.blit(cv, ox, pos)
            pos += main_size + self.gap
        return out


def VStack(children=None, gap: int = 0, bg=None, align: str = "left",
           valign: str = "top") -> Stack:
    """Vertical stack: children flow top->bottom. Cross axis = width."""
    return Stack(children=list(children or []), gap=gap, bg=bg,
                 align=align, valign=valign, horizontal=False)


def HStack(children=None, gap: int = 0, bg=None, align: str = "left",
           valign: str = "top") -> Stack:
    """Horizontal stack (flex row): children flow left->right. fr shares width."""
    return Stack(children=list(children or []), gap=gap, bg=bg,
                 align=align, valign=valign, horizontal=True)


# --------------------------------------------------------------------------
# Grid
# --------------------------------------------------------------------------
@dataclass
class Grid:
    """A rows x cols grid. ``cols``/``rows`` are track specs (int/Fr/'auto').

    ``cells`` is a flat row-major list of children (missing cells render blank).
    ``col_gap``/``row_gap`` add spacing. Column widths and row heights are each
    resolved with the carry-remainder algorithm.
    """
    cells: list = field(default_factory=list)
    cols: list = field(default_factory=list)   # per-column specs
    rows: list = field(default_factory=list)   # per-row specs
    col_gap: int = 1
    row_gap: int = 0
    bg: object = None

    width = None   # so Stack treats a nested Grid as flex
    height = None

    @property
    def ncols(self) -> int:
        return len(self.cols)

    @property
    def nrows(self) -> int:
        return len(self.rows)

    def _child_at(self, r: int, c: int):
        idx = r * self.ncols + c
        return self.cells[idx] if idx < len(self.cells) else None

    def measure(self, avail_w: int, avail_h: int) -> tuple[int, int]:
        col_nat = [0] * self.ncols
        row_nat = [0] * self.nrows
        for r in range(self.nrows):
            for c in range(self.ncols):
                ch = self._child_at(r, c)
                if ch is None:
                    continue
                w, h = ch.measure(avail_w, avail_h)
                col_nat[c] = max(col_nat[c], w)
                row_nat[r] = max(row_nat[r], h)
        w = sum(col_nat) + self.col_gap * max(0, self.ncols - 1)
        h = sum(row_nat) + self.row_gap * max(0, self.nrows - 1)
        return (w, h)

    def render(self, region_w: int, region_h: int) -> Canvas:
        bg = parse_color(self.bg)
        out = Canvas(region_w, region_h, bg=bg)
        col_nat = [0] * self.ncols
        row_nat = [0] * self.nrows
        for r in range(self.nrows):
            for c in range(self.ncols):
                ch = self._child_at(r, c)
                if ch is None:
                    continue
                w, h = ch.measure(region_w, region_h)
                col_nat[c] = max(col_nat[c], w)
                row_nat[r] = max(row_nat[r], h)

        col_w = resolve_tracks(region_w, self.cols, col_nat, gap=self.col_gap)
        row_h = resolve_tracks(region_h, self.rows, row_nat, gap=self.row_gap)

        y = 0
        for r in range(self.nrows):
            x = 0
            for c in range(self.ncols):
                ch = self._child_at(r, c)
                cw, chh = col_w[c], row_h[r]
                if ch is not None and cw > 0 and chh > 0:
                    out.blit(ch.render(cw, chh), x, y)
                x += cw + self.col_gap
            y += row_h[r] + self.row_gap
        return out


def grid(cells, ncols: int, col_spec="1fr", row_spec="auto",
         col_gap: int = 1, row_gap: int = 0, bg=None) -> Grid:
    """Build a Grid from a flat *cells* list wrapped into *ncols* columns."""
    nrows = (len(cells) + ncols - 1) // ncols
    cols = [col_spec] * ncols
    rows = [row_spec] * nrows
    return Grid(cells=list(cells), cols=cols, rows=rows,
                col_gap=col_gap, row_gap=row_gap, bg=bg)


# --------------------------------------------------------------------------
# Page: the full-screen root
# --------------------------------------------------------------------------
@dataclass
class Page:
    """A fixed-size root that renders its single ``child`` and serializes once.

    This is what you print (or feed to the pyte->PNG harness): call
    :meth:`to_ansi` for a complete, tmux-safe frame string.
    """
    child: object
    width: int = 80
    height: int = 24
    bg: object = None

    def render(self) -> Canvas:
        bg = parse_color(self.bg)
        out = Canvas(self.width, self.height, bg=bg)
        if self.child is not None:
            out.blit(self.child.render(self.width, self.height), 0, 0)
        return out

    def to_ansi(self) -> str:
        return self.render().to_ansi()

    def to_lines(self) -> list[str]:
        return self.render().to_lines()