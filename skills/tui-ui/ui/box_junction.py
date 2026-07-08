"""box_junction.py — BoxGrid: structure as edge-algebra (primitive #3).

Borders / tables / trees are NOT hand-placed ``─│┌┐`` glyphs. Every cell records
the weight of its four half-edges::

    edge[N, E, S, W] in {0:none, 1:thin, 2:heavy, 3:double}

Lines only *deposit* edges (``add_h_line`` sets E/W arms along a row, ``add_v_line``
sets N/S arms down a column, ``rect`` is four lines). The glyph is then a PURE
lookup ``GLYPHS[(n, e, s, w)]`` over the full Unicode box-drawing block. Two lines
that share a cell therefore auto-connect: a rect crossed by an interior divider
grows ``┬ ┼ ┤ ├ ┴`` with zero special-casing — the junction is just the sum of the
arms that happen to meet there. Mixed weights resolve to the exact mixed glyph
where Unicode has one (``┿ ╂ ┰ …``) and to the nearest same-topology glyph where it
does not (heavy⇄double have no mixed forms). See references/RENDERING-MODEL.md §3.

Pure stdlib. Weights compose by ``max`` so a heavy line drawn over a thin one wins.
"""
from __future__ import annotations

from typing import Optional

from .core import RGB, Canvas

# -- edge weights ----------------------------------------------------------
NONE = 0
THIN = 1
HEAVY = 2
DOUBLE = 3

N, E, S, W = 0, 1, 2, 3  # arm indices into an edge tuple

# ==========================================================================
# The lookup: (n, e, s, w) arm-weight signature -> box-drawing glyph.
# Built from grouped sub-tables so the full block is auditable. Signature is
# always (North, East, South, West); a 0 arm means "no line leaves this side".
# ==========================================================================

# Straight runs and pure-weight through-lines (incl. mixed-weight straights).
_STRAIGHT = {
    (0, 1, 0, 1): "─", (0, 2, 0, 2): "━", (0, 3, 0, 3): "═",
    (1, 0, 1, 0): "│", (2, 0, 2, 0): "┃", (3, 0, 3, 0): "║",
    (0, 2, 0, 1): "╼", (0, 1, 0, 2): "╾",  # left-thin/right-heavy & reverse
    (1, 0, 2, 0): "╽", (2, 0, 1, 0): "╿",  # up-thin/down-heavy & reverse
}

# Single-arm stubs (line ends). Only thin+heavy exist in Unicode.
_STUBS = {
    (0, 0, 0, 1): "╴", (1, 0, 0, 0): "╵", (0, 1, 0, 0): "╶", (0, 0, 1, 0): "╷",
    (0, 0, 0, 2): "╸", (2, 0, 0, 0): "╹", (0, 2, 0, 0): "╺", (0, 0, 2, 0): "╻",
}

# Corners (2 adjacent arms). Pure thin/heavy/double + every thin⇄heavy and
# thin⇄double mix Unicode provides. (heavy⇄double corners do not exist.)
_CORNERS = {
    # down+right (┌ family): (0, E, S, 0)
    (0, 1, 1, 0): "┌", (0, 2, 1, 0): "┍", (0, 1, 2, 0): "┎", (0, 2, 2, 0): "┏",
    (0, 3, 1, 0): "╒", (0, 1, 3, 0): "╓", (0, 3, 3, 0): "╔",
    # down+left (┐ family): (0, 0, S, W)
    (0, 0, 1, 1): "┐", (0, 0, 1, 2): "┑", (0, 0, 2, 1): "┒", (0, 0, 2, 2): "┓",
    (0, 0, 1, 3): "╕", (0, 0, 3, 1): "╖", (0, 0, 3, 3): "╗",
    # up+right (└ family): (N, E, 0, 0)
    (1, 1, 0, 0): "└", (1, 2, 0, 0): "┕", (2, 1, 0, 0): "┖", (2, 2, 0, 0): "┗",
    (1, 3, 0, 0): "╘", (3, 1, 0, 0): "╙", (3, 3, 0, 0): "╚",
    # up+left (┘ family): (N, 0, 0, W)
    (1, 0, 0, 1): "┘", (1, 0, 0, 2): "┙", (2, 0, 0, 1): "┚", (2, 0, 0, 2): "┛",
    (1, 0, 0, 3): "╛", (3, 0, 0, 1): "╜", (3, 0, 0, 3): "╝",
}

# Rounded thin corners (alternate glyphs for the four thin corners). Applied
# only when resolve(rounded=True); weight alone can't encode "rounded".
_ROUNDED = {
    (0, 1, 1, 0): "╭", (0, 0, 1, 1): "╮", (1, 1, 0, 0): "╰", (1, 0, 0, 1): "╯",
}

# Tees (3 arms). Full thin⇄heavy mix (all 2^3 per orientation) + thin⇄double.
_TEES = {
    # ├ VERTICAL AND RIGHT — signature (N, E, S, 0)
    (1, 1, 1, 0): "├", (1, 2, 1, 0): "┝", (2, 1, 1, 0): "┞", (1, 1, 2, 0): "┟",
    (2, 1, 2, 0): "┠", (2, 2, 1, 0): "┡", (1, 2, 2, 0): "┢", (2, 2, 2, 0): "┣",
    (1, 3, 1, 0): "╞", (3, 1, 3, 0): "╟", (3, 3, 3, 0): "╠",
    # ┤ VERTICAL AND LEFT — signature (N, 0, S, W)
    (1, 0, 1, 1): "┤", (1, 0, 1, 2): "┥", (2, 0, 1, 1): "┦", (1, 0, 2, 1): "┧",
    (2, 0, 2, 1): "┨", (2, 0, 1, 2): "┩", (1, 0, 2, 2): "┪", (2, 0, 2, 2): "┫",
    (1, 0, 1, 3): "╡", (3, 0, 3, 1): "╢", (3, 0, 3, 3): "╣",
    # ┬ DOWN AND HORIZONTAL — signature (0, E, S, W)
    (0, 1, 1, 1): "┬", (0, 1, 1, 2): "┭", (0, 2, 1, 1): "┮", (0, 2, 1, 2): "┯",
    (0, 1, 2, 1): "┰", (0, 1, 2, 2): "┱", (0, 2, 2, 1): "┲", (0, 2, 2, 2): "┳",
    (0, 3, 1, 3): "╤", (0, 1, 3, 1): "╥", (0, 3, 3, 3): "╦",
    # ┴ UP AND HORIZONTAL — signature (N, E, 0, W)
    (1, 1, 0, 1): "┴", (1, 1, 0, 2): "┵", (1, 2, 0, 1): "┶", (1, 2, 0, 2): "┷",
    (2, 1, 0, 1): "┸", (2, 1, 0, 2): "┹", (2, 2, 0, 1): "┺", (2, 2, 0, 2): "┻",
    (1, 3, 0, 3): "╧", (3, 1, 0, 1): "╨", (3, 3, 0, 3): "╩",
}

# Crosses (4 arms). Full thin⇄heavy mix (all 2^4) + the three thin⇄double forms.
_CROSSES = {
    (1, 1, 1, 1): "┼", (1, 1, 1, 2): "┽", (1, 2, 1, 1): "┾", (1, 2, 1, 2): "┿",
    (2, 1, 1, 1): "╀", (1, 1, 2, 1): "╁", (2, 1, 2, 1): "╂", (2, 1, 1, 2): "╃",
    (2, 2, 1, 1): "╄", (1, 1, 2, 2): "╅", (1, 2, 2, 1): "╆", (2, 2, 1, 2): "╇",
    (1, 2, 2, 2): "╈", (2, 1, 2, 2): "╉", (2, 2, 2, 1): "╊", (2, 2, 2, 2): "╋",
    (1, 3, 1, 3): "╪", (3, 1, 3, 1): "╫", (3, 3, 3, 3): "╬",
}

# The one flat table the resolver reads. Order matters only for the empty cell.
GLYPHS: dict[tuple[int, int, int, int], str] = {(0, 0, 0, 0): " "}
for _t in (_STRAIGHT, _STUBS, _CORNERS, _TEES, _CROSSES):
    GLYPHS.update(_t)


def resolve_glyph(n: int, e: int, s: int, w: int) -> str:
    """Signature -> glyph, with nearest-topology fallback for gaps (e.g. mixed
    heavy/double crosses Unicode lacks): try exact, then degrade DOUBLE->HEAVY
    ->THIN on the odd-arm-out until a glyph exists."""
    sig = (n, e, s, w)
    if sig in GLYPHS:
        return GLYPHS[sig]
    # fallback: collapse all arms toward THIN and retry, preserving topology
    for target in (HEAVY, THIN):
        cand = tuple(target if a else 0 for a in sig)
        if cand in GLYPHS:
            return GLYPHS[cand]
    return "+"  # last resort, never lose the junction entirely


class BoxGrid:
    """Structure as edge-algebra: deposit line arms, resolve() to glyphs.

    edges[y][x] = [N, E, S, W] weights. Lines only add arms; junctions are the
    sum of arms meeting in a cell, so crossings auto-connect (┼ ┬ ┤ …).
    """

    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.edges = [[[0, 0, 0, 0] for _ in range(cols)] for _ in range(rows)]

    def _bump(self, x: int, y: int, arm: int, weight: int) -> None:
        if 0 <= x < self.cols and 0 <= y < self.rows:
            self.edges[y][x][arm] = max(self.edges[y][x][arm], weight)

    def add_h_line(self, x: int, y: int, length: int, weight: int = THIN) -> None:
        """Horizontal run from (x,y) length cells: each interior cell gets E+W arms."""
        for i in range(length):
            cx = x + i
            if i > 0:
                self._bump(cx, y, W, weight)
            if i < length - 1:
                self._bump(cx, y, E, weight)

    def add_v_line(self, x: int, y: int, length: int, weight: int = THIN) -> None:
        for i in range(length):
            cy = y + i
            if i > 0:
                self._bump(x, cy, N, weight)
            if i < length - 1:
                self._bump(x, cy, S, weight)

    def rect(self, x: int, y: int, w: int, h: int, weight: int = THIN) -> None:
        self.add_h_line(x, y, w, weight)
        self.add_h_line(x, y + h - 1, w, weight)
        self.add_v_line(x, y, h, weight)
        self.add_v_line(x + w - 1, y, h, weight)

    def resolve(self) -> list[list[str]]:
        return [[resolve_glyph(*self.edges[y][x]) for x in range(self.cols)]
                for y in range(self.rows)]

    def blit_into(self, canvas: Canvas, ox: int = 0, oy: int = 0,
                  fg: Optional[RGB] = None) -> None:
        grid = self.resolve()
        for y in range(self.rows):
            for x in range(self.cols):
                g = grid[y][x]
                if g != " ":
                    canvas.set(ox + x, oy + y, g, fg=fg)
