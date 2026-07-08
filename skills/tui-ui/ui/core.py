"""tui-ui core: a cell-grid Canvas, cell-accurate width, and ANSI serialization.

This is the substrate the whole engine draws into. A screen is an integer grid of
:class:`Cell` (``char + fg + bg + attrs``); widgets and boxes composite by rendering
small :class:`Canvas` buffers and ``blit``-ing them into a parent. The root
serializes once via :meth:`Canvas.to_ansi` (run-length SGR, like fx).

Width is display-CELL width (never ``len``): CJK/fullwidth -> 2, combining -> 0,
emoji ZWJ sequences / VS16 / regional-indicator flag pairs handled so columns line
up. Uses the ``wcwidth`` package when importable (SemVer-stable ``wcswidth``); a
self-contained stdlib fallback (``unicodedata``) covers the same edge cases so the
skill runs on pure stdlib + optional pyfiglet.

Output is tmux-safe: only CSI SGR (``\\x1b[...m``) plus newlines are emitted, no
cursor moves or alt-screen — so a frame is composable, printable, and can be fed to
the same pyte->PNG harness the rest of SmartCLI uses.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, NamedTuple, Optional

try:  # optional but preferred: the SAME per-codepoint width table pyte/tmux use
    from wcwidth import wcwidth as _wcwidth_pkg  # type: ignore
except Exception:  # pragma: no cover - fallback path
    _wcwidth_pkg = None

RGB = tuple[int, int, int]

# -- text attribute bitmask ------------------------------------------------
BOLD = 1
DIM = 2
ITALIC = 4
UNDERLINE = 8
REVERSE = 16
_ATTR_SGR = ((BOLD, "1"), (DIM, "2"), (ITALIC, "3"), (UNDERLINE, "4"), (REVERSE, "7"))

RESET = "\x1b[0m"
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


# ==========================================================================
# Width: display-cell width (CJK / emoji / combining aware)
# ==========================================================================
def strip_ansi(s: str) -> str:
    """Remove CSI escape sequences so they measure as zero-width."""
    return _ANSI_RE.sub("", s)


def _char_width_stdlib(ch: str) -> int:
    """Per-codepoint cell width via unicodedata (stdlib fallback for wcwidth).

    Mirrors ``wcwidth.wcwidth`` for a single scalar so it matches what a VT
    terminal (pyte / tmux) actually advances the cursor by:
      * NUL / combining / ZWJ (U+200D) / variation selectors (U+FE0E/U+FE0F) -> 0
      * other C0/C1 controls -> -1 (unprintable)
      * East-Asian Wide/Fullwidth (incl. emoji, regional indicators) -> 2
      * everything else -> 1
    """
    o = ord(ch)
    if o == 0:
        return 0
    if o < 32 or 0x7F <= o < 0xA0:
        return -1  # control -> unprintable
    # Zero-width joiners / variation selectors advance 0 cells in the grid.
    if o == 0x200D or o == 0xFE0E or o == 0xFE0F or 0x200B <= o <= 0x200F:
        return 0
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def char_width(ch: str) -> int:
    """Terminal cell advance of a single scalar: 0, 1, or 2 (controls -> 0).

    THE per-codepoint primitive. Prefers ``wcwidth.wcwidth`` (the exact table
    pyte/tmux use) so a glyph occupies identically many cells in our Canvas as
    in the terminal that re-parses our output. Falls back to a matching stdlib
    implementation. This is deliberately per-codepoint, not grapheme-cluster:
    the terminal cell grid is per-codepoint, so a ZWJ emoji or a flag pair
    consumes the sum of its scalar widths (e.g. a regional-indicator flag = 4
    cells), and the engine must agree or every column behind it desyncs.
    """
    if not ch:
        return 0
    c0 = ch[0]
    if _wcwidth_pkg is not None:
        w = _wcwidth_pkg(c0)
        if w is not None:
            return 0 if w < 0 else w
    w = _char_width_stdlib(c0)
    return 0 if w < 0 else w


def width(s: str) -> int:
    """Display-cell width of *s* (ANSI stripped first). Never negative.

    THE width function the whole engine uses instead of ``len``. Defined as the
    per-codepoint sum of :func:`char_width`, so it is *identical* to the number
    of cells :meth:`Canvas.put_text` will occupy when drawing *s*. That identity
    is what keeps table columns / padding aligned with the rendered grid: a
    measurement can never disagree with what actually gets drawn. It also
    matches the terminal (pyte/tmux advance per codepoint via ``wcwidth``).
    """
    s = strip_ansi(s)
    return sum(char_width(ch) for ch in s)


def _visible_len_fallback(s: str) -> int:
    return sum(max(0, _char_width_stdlib(c)) for c in s)


def slice_cells(s: str, max_cells: int) -> str:
    """Take a prefix of *s* fitting in *max_cells*, never splitting a wide glyph.

    If the cut would land inside a double-width cell, stop before it (the caller
    pads with a space). Operates on the visible text; ANSI is assumed absent
    (callers strip/handle color separately).
    """
    if max_cells <= 0:
        return ""
    out = []
    used = 0
    for ch in s:
        w = char_width(ch)
        if used + w > max_cells:
            break
        out.append(ch)
        used += w
    return "".join(out)


def truncate(s: str, max_cells: int, ellipsis: str = "…") -> str:
    """Fit *s* into *max_cells*, appending an ellipsis when it overflows."""
    if width(s) <= max_cells:
        return s
    if max_cells <= 0:
        return ""
    if max_cells == 1:
        return ellipsis
    return slice_cells(s, max_cells - 1) + ellipsis


def pad(s: str, target: int, align: str = "left", fillchar: str = " ") -> str:
    """Pad (or truncate) *s* to exactly *target* display cells.

    ``align`` is left/right/center; extra odd cell goes right (matches Rich).
    """
    w = width(s)
    if w > target:
        s = truncate(s, target)
        w = width(s)
    gap = target - w
    if gap <= 0:
        return s
    if align == "right":
        return fillchar * gap + s
    if align == "center":
        left = gap // 2
        return fillchar * left + s + fillchar * (gap - left)
    return s + fillchar * gap


# ==========================================================================
# Color helpers (truecolor SGR)
# ==========================================================================
def rgb(r: int, g: int, b: int, bg: bool = False) -> str:
    """Truecolor SGR string. Foreground by default, background when ``bg=True``."""
    return "\x1b[%d;2;%d;%d;%dm" % (48 if bg else 38, int(r), int(g), int(b))


def clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else 1.0 if t > 1.0 else t


def lerp_color(c0: RGB, c1: RGB, t: float) -> RGB:
    """Per-channel integer interpolation between two RGB colors, ``t`` in 0..1."""
    t = clamp01(t)
    return (int(c0[0] + (c1[0] - c0[0]) * t),
            int(c0[1] + (c1[1] - c0[1]) * t),
            int(c0[2] + (c1[2] - c0[2]) * t))


def gradient(stops: tuple[RGB, ...], t: float) -> RGB:
    """Sample a multi-stop gradient. ``t`` in 0..1 maps across all *stops* evenly."""
    n = len(stops)
    if n == 0:
        return (255, 255, 255)
    if n == 1:
        return stops[0]
    t = clamp01(t)
    scaled = t * (n - 1)
    i = int(scaled)
    if i >= n - 1:
        return stops[-1]
    return lerp_color(stops[i], stops[i + 1], scaled - i)


def parse_color(spec) -> Optional[RGB]:
    """Coerce a color spec to an RGB triple (or None for 'no color').

    Accepts an ``(r,g,b)`` tuple, ``'#RRGGBB'`` / ``'RRGGBB'`` hex, or None.
    """
    if spec is None:
        return None
    if isinstance(spec, tuple):
        return (int(spec[0]), int(spec[1]), int(spec[2]))
    h = str(spec).strip().lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    raise ValueError(f"bad color spec: {spec!r}")


# ==========================================================================
# Cell + Canvas
# ==========================================================================
@dataclass
class Cell:
    """One grid cell: a printable char plus its style. ``cont`` marks the
    trailing half of a wide (double-width) glyph — it is skipped on serialize."""

    char: str = " "
    fg: Optional[RGB] = None
    bg: Optional[RGB] = None
    attrs: int = 0
    cont: bool = False  # continuation cell of a wide glyph to the left


def _style_key(c: Cell):
    return (c.fg, c.bg, c.attrs)


def _sgr(fg: Optional[RGB], bg: Optional[RGB], attrs: int) -> str:
    """Build one SGR sequence for a (fg,bg,attrs) style. Empty => default."""
    parts: list[str] = []
    for bit, code in _ATTR_SGR:
        if attrs & bit:
            parts.append(code)
    seq = ""
    if parts:
        seq += "\x1b[" + ";".join(parts) + "m"
    if fg is not None:
        seq += rgb(*fg)
    if bg is not None:
        seq += rgb(*bg, bg=True)
    return seq


class Canvas:
    """A fixed-size grid of :class:`Cell` you draw into, then serialize.

    Coordinates are ``(x, y)`` with origin top-left, ``x`` across columns.
    Out-of-bounds writes are clipped silently. Wide glyphs occupy two cells:
    the glyph cell plus a ``cont`` cell to its right (never serialized), so a
    CJK/emoji char never desyncs the columns behind it.
    """

    def __init__(self, width_cells: int, height: int,
                 fill: str = " ", fg: Optional[RGB] = None,
                 bg: Optional[RGB] = None):
        self.w = max(0, int(width_cells))
        self.h = max(0, int(height))
        self._default = (fg, bg)
        self.grid: list[list[Cell]] = [
            [Cell(fill, fg, bg) for _ in range(self.w)] for _ in range(self.h)
        ]

    # -- primitives --------------------------------------------------------
    def cell(self, x: int, y: int) -> Optional[Cell]:
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.grid[y][x]
        return None

    def set(self, x: int, y: int, char: str, fg=None, bg=None, attrs: int = 0) -> None:
        """Write a single character cell (assumed width 1). Clipped if OOB."""
        if 0 <= x < self.w and 0 <= y < self.h:
            self.grid[y][x] = Cell(char, fg, bg, attrs, cont=False)

    def put_text(self, x: int, y: int, text: str, fg=None, bg=None,
                 attrs: int = 0, max_cells: Optional[int] = None) -> int:
        """Draw *text* starting at (x, y), wide-char aware. Returns cells written.

        Stops at the row edge or *max_cells*. A wide glyph writes its cell plus a
        continuation cell; if only one cell of room remains it writes a space
        instead of splitting the glyph.
        """
        if y < 0 or y >= self.h:
            return 0
        limit = self.w - x if max_cells is None else min(self.w - x, max_cells)
        if limit <= 0:
            return 0
        cx = x
        used = 0
        for ch in text:
            if ch == "\n":
                break
            cw = char_width(ch)
            if cw == 0:
                # combining/zero-width: merge into previous cell if possible
                if cx - 1 >= 0 and cx - 1 < self.w and used > 0:
                    prev = self.grid[y][cx - 1]
                    prev.char = prev.char + ch
                continue
            if used + cw > limit or cx >= self.w:
                break
            if cw == 2:
                if cx + 1 >= self.w:  # no room for the pair: pad a space
                    self.grid[y][cx] = Cell(" ", fg, bg, attrs)
                    used += 1
                    break
                self.grid[y][cx] = Cell(ch, fg, bg, attrs, cont=False)
                self.grid[y][cx + 1] = Cell("", fg, bg, attrs, cont=True)
                cx += 2
                used += 2
            else:
                self.grid[y][cx] = Cell(ch, fg, bg, attrs, cont=False)
                cx += 1
                used += 1
        return used

    def fill_rect(self, x: int, y: int, w: int, h: int, char: str = " ",
                  fg=None, bg=None, attrs: int = 0) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if 0 <= xx < self.w and 0 <= yy < self.h:
                    self.grid[yy][xx] = Cell(char, fg, bg, attrs)

    def blit(self, child: "Canvas", x: int, y: int) -> None:
        """Composite *child* onto this canvas at (x, y), respecting wide cells.

        A continuation cell copies faithfully; if a child's left edge lands on a
        continuation cell of an existing wide glyph, the orphaned lead cell is
        blanked so no half-glyph is left behind.
        """
        for cy in range(child.h):
            ty = y + cy
            if ty < 0 or ty >= self.h:
                continue
            for cx in range(child.w):
                tx = x + cx
                if tx < 0 or tx >= self.w:
                    continue
                src = child.grid[cy][cx]
                # Copy the cell.
                self.grid[ty][tx] = Cell(src.char, src.fg, src.bg, src.attrs, src.cont)
            # Heal a wide glyph we may have cut at the right edge of the child.
            rx = x + child.w
            if 0 <= rx < self.w and self.grid[ty][rx].cont:
                self.grid[ty][rx] = Cell(" ", *self._default)
            lx = x - 1
            if 0 <= lx < self.w and 0 <= x < self.w and self.grid[ty][x].cont:
                self.grid[ty][lx] = Cell(" ", *self._default)

    # -- serialization -----------------------------------------------------
    def to_ansi(self, reset_each_line: bool = True) -> str:
        """Serialize to an ANSI string: run-length SGR, one line per row.

        Only emits a new SGR when the style changes (run-length like fx), resets
        at end of each line so trailing bg never bleeds. Continuation cells are
        skipped (their glyph was already emitted). tmux-safe: SGR + newlines only.
        """
        lines: list[str] = []
        for row in self.grid:
            buf: list[str] = []
            cur = None
            for c in row:
                if c.cont:
                    continue
                key = _style_key(c)
                if key != cur:
                    buf.append(RESET)
                    buf.append(_sgr(c.fg, c.bg, c.attrs))
                    cur = key
                buf.append(c.char if c.char else " ")
            if reset_each_line:
                buf.append(RESET)
            lines.append("".join(buf))
        return "\n".join(lines)

    def to_lines(self) -> list[str]:
        """Plain text rows (no color), wide-aware. Useful for tests/asserts."""
        out = []
        for row in self.grid:
            s = "".join("" if c.cont else (c.char if c.char else " ") for c in row)
            out.append(s)
        return out

    def __str__(self) -> str:
        return self.to_ansi()


# ==========================================================================
# Box-drawing glyph tables (per style, keyed by role) — from research §3
# ==========================================================================
# roles: h v tl tr bl br tee_l tee_r tee_d tee_u cross
BOX_STYLES: dict[str, dict[str, str]] = {
    "single": dict(h="─", v="│", tl="┌", tr="┐", bl="└", br="┘",
                   tee_l="┤", tee_r="├", tee_d="┬", tee_u="┴", cross="┼"),
    "rounded": dict(h="─", v="│", tl="╭", tr="╮", bl="╰", br="╯",
                    tee_l="┤", tee_r="├", tee_d="┬", tee_u="┴", cross="┼"),
    "heavy": dict(h="━", v="┃", tl="┏", tr="┓", bl="┗", br="┛",
                  tee_l="┫", tee_r="┣", tee_d="┳", tee_u="┻", cross="╋"),
    "double": dict(h="═", v="║", tl="╔", tr="╗", bl="╚", br="╝",
                   tee_l="╣", tee_r="╠", tee_d="╦", tee_u="╩", cross="╬"),
    "ascii": dict(h="-", v="|", tl="+", tr="+", bl="+", br="+",
                  tee_l="+", tee_r="+", tee_d="+", tee_u="+", cross="+"),
}
BOX_STYLES["none"] = dict.fromkeys(BOX_STYLES["single"], " ")

# 1/8-cell horizontal bar glyphs for progress meters (U+2588..U+258F).
BAR_EIGHTHS = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"]
BAR_FULL = "█"


def draw_border(canvas: Canvas, x: int, y: int, w: int, h: int, style: str = "single",
                fg=None, bg=None, attrs: int = 0) -> None:
    """Draw a rectangular border of *style* on *canvas*. Corners + edges only."""
    if w < 2 or h < 2:
        return
    g = BOX_STYLES.get(style, BOX_STYLES["single"])
    canvas.set(x, y, g["tl"], fg, bg, attrs)
    canvas.set(x + w - 1, y, g["tr"], fg, bg, attrs)
    canvas.set(x, y + h - 1, g["bl"], fg, bg, attrs)
    canvas.set(x + w - 1, y + h - 1, g["br"], fg, bg, attrs)
    for xx in range(x + 1, x + w - 1):
        canvas.set(xx, y, g["h"], fg, bg, attrs)
        canvas.set(xx, y + h - 1, g["h"], fg, bg, attrs)
    for yy in range(y + 1, y + h - 1):
        canvas.set(x, yy, g["v"], fg, bg, attrs)
        canvas.set(x + w - 1, yy, g["v"], fg, bg, attrs)


# ==========================================================================
# Themes: named palettes with semantic slots (page-level styling)
# ==========================================================================
@dataclass(frozen=True)
class Theme:
    """A page palette. Semantic slots map web-ish design tokens to RGB.

    ``stops`` runs base->accent for gradients (progress bars, banners).
    """
    name: str
    stops: tuple[RGB, ...]
    bg: RGB = (12, 12, 12)
    fg: RGB = (200, 200, 200)
    muted: RGB = (120, 120, 120)
    border: RGB = (90, 90, 110)
    accent: RGB = (110, 180, 255)
    ok: RGB = (80, 200, 120)
    warn: RGB = (240, 190, 60)
    err: RGB = (230, 80, 90)

    def color_at(self, t: float) -> RGB:
        return gradient(self.stops, t)

    @property
    def primary(self) -> RGB:
        return self.stops[-1]


THEMES: dict[str, Theme] = {
    "dashboard": Theme(
        "dashboard",
        stops=((30, 60, 120), (60, 130, 200), (120, 200, 240), (200, 240, 255)),
        bg=(14, 16, 22), fg=(210, 216, 228), muted=(120, 130, 150),
        border=(70, 90, 130), accent=(110, 190, 255),
        ok=(90, 210, 130), warn=(245, 195, 70), err=(240, 90, 100)),
    "synthwave": Theme(
        "synthwave",
        stops=((90, 10, 120), (200, 30, 160), (255, 70, 130), (60, 220, 240)),
        bg=(20, 10, 34), fg=(240, 220, 245), muted=(150, 120, 170),
        border=(150, 60, 180), accent=(255, 90, 200),
        ok=(120, 240, 200), warn=(255, 200, 90), err=(255, 80, 140)),
    "forest": Theme(
        "forest",
        stops=((20, 60, 30), (40, 120, 60), (110, 190, 90), (220, 240, 170)),
        bg=(12, 20, 14), fg=(214, 228, 208), muted=(120, 140, 120),
        border=(70, 110, 80), accent=(140, 210, 120),
        ok=(120, 220, 120), warn=(230, 200, 90), err=(230, 110, 90)),
    "mono": Theme(
        "mono",
        stops=((40, 40, 40), (120, 120, 120), (200, 200, 200), (255, 255, 255)),
        bg=(10, 10, 10), fg=(220, 220, 220), muted=(120, 120, 120),
        border=(120, 120, 120), accent=(255, 255, 255),
        ok=(200, 200, 200), warn=(200, 200, 200), err=(255, 255, 255)),
    "amber": Theme(
        "amber",
        stops=((60, 30, 0), (160, 90, 10), (240, 160, 40), (255, 225, 150)),
        bg=(22, 16, 8), fg=(240, 220, 180), muted=(150, 130, 90),
        border=(150, 100, 40), accent=(255, 190, 80),
        ok=(200, 220, 120), warn=(255, 200, 90), err=(240, 120, 70)),
}
DEFAULT_THEME = "dashboard"


def get_theme(name: Optional[str]) -> Theme:
    if not name:
        return THEMES[DEFAULT_THEME]
    return THEMES.get(name.lower().strip(), THEMES[DEFAULT_THEME])


def theme_names() -> list[str]:
    return list(THEMES.keys())
