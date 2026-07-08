"""Big block ASCII text with a truecolor gradient (legacy cmd-art effect).

Static banner by default; ``--set shimmer=true`` animates an HSV hue sweep.
Uses pyfiglet when importable, else the built-in 5-row block font.
"""
from __future__ import annotations

import colorsys

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register

FONT = {
    ' ': ["   ", "   ", "   ", "   ", "   "],
    'A': [" ### ", "#   #", "#####", "#   #", "#   #"],
    'B': ["#### ", "#   #", "#### ", "#   #", "#### "],
    'C': [" ####", "#    ", "#    ", "#    ", " ####"],
    'D': ["#### ", "#   #", "#   #", "#   #", "#### "],
    'E': ["#####", "#    ", "###  ", "#    ", "#####"],
    'F': ["#####", "#    ", "###  ", "#    ", "#    "],
    'G': [" ####", "#    ", "#  ##", "#   #", " ####"],
    'H': ["#   #", "#   #", "#####", "#   #", "#   #"],
    'I': ["###", " # ", " # ", " # ", "###"],
    'J': ["  ###", "   # ", "   # ", "#  # ", " ##  "],
    'K': ["#   #", "#  # ", "###  ", "#  # ", "#   #"],
    'L': ["#    ", "#    ", "#    ", "#    ", "#####"],
    'M': ["#   #", "## ##", "# # #", "#   #", "#   #"],
    'N': ["#   #", "##  #", "# # #", "#  ##", "#   #"],
    'O': [" ### ", "#   #", "#   #", "#   #", " ### "],
    'P': ["#### ", "#   #", "#### ", "#    ", "#    "],
    'Q': [" ### ", "#   #", "#   #", "#  # ", " ## #"],
    'R': ["#### ", "#   #", "#### ", "#  # ", "#   #"],
    'S': [" ####", "#    ", " ### ", "    #", "#### "],
    'T': ["#####", "  #  ", "  #  ", "  #  ", "  #  "],
    'U': ["#   #", "#   #", "#   #", "#   #", " ### "],
    'V': ["#   #", "#   #", "#   #", " # # ", "  #  "],
    'W': ["#   #", "#   #", "# # #", "## ##", "#   #"],
    'X': ["#   #", " # # ", "  #  ", " # # ", "#   #"],
    'Y': ["#   #", " # # ", "  #  ", "  #  ", "  #  "],
    'Z': ["#####", "   # ", "  #  ", " #   ", "#####"],
    '0': [" ### ", "#  ##", "# # #", "##  #", " ### "],
    '1': ["  #  ", " ##  ", "  #  ", "  #  ", " ### "],
    '2': [" ### ", "#   #", "  ## ", " #   ", "#####"],
    '3': ["#### ", "    #", " ### ", "    #", "#### "],
    '4': ["#   #", "#   #", "#####", "    #", "    #"],
    '5': ["#####", "#    ", "#### ", "    #", "#### "],
    '6': [" ### ", "#    ", "#### ", "#   #", " ### "],
    '7': ["#####", "   # ", "  #  ", " #   ", "#    "],
    '8': [" ### ", "#   #", " ### ", "#   #", " ### "],
    '9': [" ### ", "#   #", " ####", "    #", " ### "],
}


def block_text(s, gutter=1):
    """Render *s* with the built-in 5-row block font -> list of 5 strings."""
    s = s.upper()
    rows = ["", "", "", "", ""]
    sep = " " * gutter
    for ch in s:
        g = FONT.get(ch, FONT[' '])
        w = max(len(line) for line in g)
        for i in range(5):
            rows[i] += g[i].ljust(w) + sep
    return [r.rstrip() for r in rows]


def big_text(s, font="standard"):
    """pyfiglet when available, else the stdlib block font. -> list of lines."""
    try:
        from pyfiglet import Figlet
        return Figlet(font=font).renderText(s).rstrip("\n").split("\n")
    except Exception:
        return block_text(s)


def hgrad(lines, c0, c1, phase=None, theme=None):
    """Horizontal gradient across an assembled text block.

    Priority: ``phase`` (HSV shimmer sweep) > ``theme`` (multi-stop gradient)
    > two-color ``c0``->``c1`` lerp.
    """
    W = max((len(l) for l in lines), default=1)

    def color_at(c):
        t = 0.0 if W <= 1 else c / (W - 1)
        if phase is not None:
            h = (t + phase) % 1.0
            r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
            return (int(r * 255), int(g * 255), int(b * 255))
        if theme is not None:
            return theme.color_at(t)
        return (int(c0[0] + (c1[0] - c0[0]) * t),
                int(c0[1] + (c1[1] - c0[1]) * t),
                int(c0[2] + (c1[2] - c0[2]) * t))

    out = []
    for line in lines:
        buf, last = [], None
        for c, ch in enumerate(line.ljust(W)):
            col = color_at(c)
            if col != last:
                buf.append(rgb(*col))
                last = col
            buf.append(ch)
        out.append("".join(buf) + RESET)
    return "\n".join(out)


@register
class Text3D(Effect):
    name = "text3d"
    aliases = ("banner",)
    description = "Big figlet/block banner with a horizontal gradient; shimmer animates."
    tags = ("text", "banner", "classic")
    params = (
        Param("text", "str", "SMARTCLI", "the text to render"),
        Param("font", "str", "standard", "pyfiglet font name (fallback: block font)"),
        Param("from", "color", None, "gradient start hex (default: theme stops)"),
        Param("to", "color", None, "gradient end hex (default: theme stops)"),
        Param("shimmer", "bool", False, "animate an HSV hue sweep"),
    )

    @classmethod
    def is_animated(cls, params: dict) -> bool:
        return bool(params.get("shimmer"))

    def setup(self) -> None:
        self._lines = None
        self._key = None

    def _text_lines(self, p):
        key = (p["text"], p["font"])
        if self._key != key:
            self._lines = big_text(p["text"], p["font"])
            self._key = key
        return self._lines

    def render(self, ctx: FrameCtx) -> str:
        p = ctx.params
        lines = self._text_lines(p)
        # Fit the banner to the frame: clip each block row to ctx.width and cap
        # the number of rows at ctx.height so a big font never spills past the
        # right edge (which the terminal would wrap) or the bottom of the frame.
        # Colors are applied AFTER clipping, so gradient stops still span the
        # visible width. (Same fit contract as gradient_text/banner_scroll.)
        if ctx.height > 0:
            lines = lines[:ctx.height]
        if ctx.width > 0:
            lines = [ln[:ctx.width] for ln in lines]
        # Pad to the full frame height (blank rows below the banner) so the
        # frame always covers ctx.height rows -- matches banner_scroll /
        # gradient_text and keeps the play loop's overwrite fully deterministic.
        if ctx.height > 0 and len(lines) < ctx.height:
            lines = lines + [""] * (ctx.height - len(lines))
        c0, c1 = p["from"], p["to"]
        phase = (ctx.t * 0.3) % 1.0 if p["shimmer"] else None
        if c0 is not None and c1 is not None and phase is None:
            return hgrad(lines, c0, c1)
        return hgrad(lines, c0 or (255, 80, 0), c1 or (0, 180, 255),
                     phase=phase, theme=None if phase is not None else ctx.theme)
