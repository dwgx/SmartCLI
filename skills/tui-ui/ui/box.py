"""box.py — the CSS-like box model on a cell grid.

A :class:`Box` wraps content in the CSS nesting order: **margin -> border ->
padding -> content**. Borders are *cells* (1 per present side), padding is the CSS
4-tuple ``(top, right, bottom, left)``, and ``box-sizing`` defaults to
``border-box`` (Textual's default): the requested ``width``/``height`` is the border
box, and content = width - gutter. See research §1.

``width``/``height`` accept:
  * an ``int``           -> fixed cells
  * ``"auto"``           -> size to content
  * ``Fr(n)`` / ``"2fr"``-> flexible; resolved by the parent layout (see layout.py)
  * ``"50%"``            -> percent of the region handed down

A Box renders into an exact region via :meth:`render` -> :class:`~ui.core.Canvas`,
and reports its natural size via :meth:`measure` so parents can resolve ``fr``/auto.
Content is anything with ``measure(w,h)`` + ``render(w,h)`` (a widget), a plain
string, or a list of strings (each a line).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional, Union

from . import core
from .core import Canvas, parse_color, width as cell_width


# --------------------------------------------------------------------------
# Dimension units
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Fr:
    """A flexible track weight (CSS ``fr``). ``Fr(2)`` grows twice as fast."""
    value: float = 1.0


Dim = Union[int, str, Fr, None]  # int | 'auto' | '50%' | Fr | '2fr' | None


def parse_dim(d: Dim) -> Dim:
    """Normalize a dimension spec to int | 'auto' | Fr | ('pct', float) | None."""
    if d is None or isinstance(d, (int, Fr)):
        return d
    s = str(d).strip().lower()
    if s in ("auto", ""):
        return "auto"
    if s.endswith("fr"):
        return Fr(float(s[:-2] or "1"))
    if s.endswith("%"):
        return ("pct", float(s[:-1]))
    return int(s)


def resolve_dim(d: Dim, available: int, natural: int) -> Optional[int]:
    """Resolve a dimension to concrete cells given the region + natural size.

    Returns None for ``fr`` (the parent layout must resolve those).
    """
    d = parse_dim(d)
    if d is None or d == "auto":
        return natural
    if isinstance(d, int):
        return d
    if isinstance(d, Fr):
        return None
    if isinstance(d, tuple) and d[0] == "pct":
        return max(0, round(available * d[1] / 100.0))
    return natural


def _as_quad(v) -> tuple[int, int, int, int]:
    """Coerce a padding/margin spec to (top, right, bottom, left), CSS arity."""
    if v is None:
        return (0, 0, 0, 0)
    if isinstance(v, int):
        return (v, v, v, v)
    t = tuple(v)
    if len(t) == 1:
        return (t[0], t[0], t[0], t[0])
    if len(t) == 2:
        return (t[0], t[1], t[0], t[1])
    if len(t) == 3:
        return (t[0], t[1], t[2], t[1])
    return (t[0], t[1], t[2], t[3])


# --------------------------------------------------------------------------
# Content adapters: normalize str / list[str] / widget to a render protocol
# --------------------------------------------------------------------------
def _content_lines(content) -> Optional[list[str]]:
    if content is None:
        return [""]
    if isinstance(content, str):
        return content.split("\n")
    if isinstance(content, (list, tuple)) and all(isinstance(x, str) for x in content):
        return list(content)
    return None  # a renderable widget


def _measure_content(content, avail_w: int, avail_h: int) -> tuple[int, int]:
    """Natural (w, h) of content in cells."""
    lines = _content_lines(content)
    if lines is not None:
        w = max((cell_width(l) for l in lines), default=0)
        return w, len(lines)
    return content.measure(avail_w, avail_h)


def _crop(cv: Canvas, w: int, h: int, fg, bg) -> Canvas:
    """Return a w x h canvas holding the top-left region of *cv*."""
    out = Canvas(w, h, fg=fg, bg=bg)
    out.blit(cv, 0, 0)  # blit clips to out's bounds
    return out


def _render_content(content, w: int, h: int, fg, bg) -> Canvas:
    """Render content into a w x h canvas."""
    lines = _content_lines(content)
    if lines is not None:
        cv = Canvas(w, h, fg=fg, bg=bg)
        for i, line in enumerate(lines[:h]):
            cv.put_text(0, i, line, fg=fg, bg=bg)
        return cv
    return content.render(w, h)


# --------------------------------------------------------------------------
# Box
# --------------------------------------------------------------------------
@dataclass
class Box:
    """A styled box: content wrapped in padding + border + margin.

    All color specs accept ``(r,g,b)`` tuples or ``'#RRGGBB'`` strings.
    """
    content: object = None
    width: Dim = "auto"
    height: Dim = "auto"
    padding: object = 0                 # int | (v,h) | (t,r,b,l)
    margin: object = 0
    border: Optional[str] = None        # single/rounded/heavy/double/ascii/none
    border_fg: object = None
    fg: object = None
    bg: object = None
    align: str = "left"                 # horizontal content align: left/center/right
    valign: str = "top"                 # vertical: top/middle/bottom
    title: Optional[str] = None
    title_align: str = "left"

    # -- geometry helpers --------------------------------------------------
    @property
    def _pad(self) -> tuple[int, int, int, int]:
        return _as_quad(self.padding)

    @property
    def _mar(self) -> tuple[int, int, int, int]:
        return _as_quad(self.margin)

    @property
    def _bord(self) -> int:
        return 0 if not self.border or self.border == "none" else 1

    def gutter(self) -> tuple[int, int]:
        """(horizontal, vertical) cells consumed by border+padding."""
        pt, pr, pb, pl = self._pad
        b = self._bord
        return (pl + pr + 2 * b, pt + pb + 2 * b)

    def margin_size(self) -> tuple[int, int]:
        mt, mr, mb, ml = self._mar
        return (ml + mr, mt + mb)

    # -- measurement -------------------------------------------------------
    def measure(self, avail_w: int, avail_h: int) -> tuple[int, int]:
        """Natural outer size (INCLUDING margin) this box wants, in cells."""
        gw, gh = self.gutter()
        mw, mh = self.margin_size()
        inner_w = max(0, avail_w - gw - mw)
        inner_h = max(0, avail_h - gh - mh)
        cw, ch = _measure_content(self.content, inner_w, inner_h)

        rw = resolve_dim(self.width, avail_w, cw + gw)
        rh = resolve_dim(self.height, avail_h, ch + gh)
        border_w = (cw + gw) if rw is None else rw
        border_h = (ch + gh) if rh is None else rh
        return (border_w + mw, border_h + mh)

    def content_width_for(self, border_w: int) -> int:
        gw, _ = self.gutter()
        return max(0, border_w - gw)

    # -- render ------------------------------------------------------------
    def render(self, region_w: int, region_h: int) -> Canvas:
        """Render the box into an exact ``region_w x region_h`` canvas.

        The margin is transparent space inside the region; the border box is
        placed at the margin offset. Content is aligned within the padding box.
        """
        fg = parse_color(self.fg)
        bg = parse_color(self.bg)
        bfg = parse_color(self.border_fg) if self.border_fg is not None else fg
        out = Canvas(region_w, region_h, fg=fg, bg=bg)

        mt, mr, mb, ml = self._mar
        pt, pr, pb, pl = self._pad
        b = self._bord

        bx, by = ml, mt
        bw = max(0, region_w - ml - mr)
        bh = max(0, region_h - mt - mb)
        if bw <= 0 or bh <= 0:
            return out

        # Paint border-box background.
        out.fill_rect(bx, by, bw, bh, " ", fg=fg, bg=bg)

        # Border.
        if b:
            core.draw_border(out, bx, by, bw, bh, self.border, fg=bfg, bg=bg)
            if self.title:
                self._draw_title(out, bx, by, bw, bfg, bg)

        # Content box geometry.
        cx = bx + b + pl
        cy = by + b + pt
        cw = max(0, bw - 2 * b - pl - pr)
        chh = max(0, bh - 2 * b - pt - pb)
        if cw <= 0 or chh <= 0:
            return out

        # Render content, then CLIP to the content region so nothing overflows
        # onto the border (widgets may render taller than requested).
        child = _render_content(self.content, cw, chh, fg, bg)
        if child.w > cw or child.h > chh:
            child = _crop(child, cw, chh, fg, bg)
        # Vertical alignment offset.
        used_h = min(child.h, chh)
        if self.valign == "middle":
            oy = (chh - used_h) // 2
        elif self.valign == "bottom":
            oy = chh - used_h
        else:
            oy = 0
        out.blit(child, cx, cy + max(0, oy))
        return out

    def _draw_title(self, out: Canvas, bx: int, by: int, bw: int, fg, bg) -> None:
        avail = bw - 4  # leave a glyph + space on each side
        if avail <= 0:
            return
        label = " " + core.truncate(self.title, avail) + " "
        lw = cell_width(label)
        if self.title_align == "center":
            sx = bx + (bw - lw) // 2
        elif self.title_align == "right":
            sx = bx + bw - 2 - lw
        else:
            sx = bx + 2
        out.put_text(sx, by, label, fg=fg, bg=bg, attrs=core.BOLD)
