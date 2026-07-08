"""Plasma / interference wave field (legacy cmd-art effect, framework port).

Sum-of-sines field (Lode Vandevenne's classic), rendered as truecolor
BACKGROUND cells so the whole screen becomes the canvas.
"""
from __future__ import annotations

import colorsys
import math

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register


def plasma_frame(t, width=80, height=40, palette="hsv", theme=None):
    """One plasma frame. ``palette``: hsv | rgb | theme (theme gradient)."""
    cx, cy = width / 2.0, height / 2.0
    lines = []
    for y in range(height):
        row = []
        last = None
        for x in range(width):
            v = (math.sin(x * 0.10 + t)
                 + math.sin(y * 0.15 + t * 0.8)
                 + math.sin((x + y) * 0.08 + t * 1.2)
                 + math.sin(math.hypot(x - cx, y - cy) * 0.12 - t))
            n = (v + 4.0) / 8.0
            if palette == "rgb":
                r = 128 + 127 * math.sin(math.pi * n)
                g = 128 + 127 * math.sin(math.pi * n + 2 * math.pi / 3)
                b = 128 + 127 * math.sin(math.pi * n + 4 * math.pi / 3)
                c = (int(r), int(g), int(b))
            elif palette == "theme" and theme is not None:
                if theme.hsv:
                    c = theme.cycle(n)
                else:
                    c = theme.color_at(n)
            else:
                rf, gf, bf = colorsys.hsv_to_rgb(n, 1.0, 1.0)
                c = (int(rf * 255), int(gf * 255), int(bf * 255))
            if c != last:
                row.append(rgb(*c, bg=True))
                last = c
            row.append(" ")
        lines.append("".join(row) + RESET)
    return "\n".join(lines)


@register
class Plasma(Effect):
    name = "plasma"
    aliases = ("wave",)
    description = "Full-screen interference wave field (sum of sines, bg-colored cells)."
    tags = ("field", "classic", "psychedelic")
    default_fps = 24.0
    params = (
        Param("palette", "str", "theme", "color source", choices=("theme", "hsv", "rgb")),
    )

    def render(self, ctx: FrameCtx) -> str:
        return plasma_frame(ctx.t, width=ctx.width, height=ctx.height,
                            palette=ctx.params["palette"], theme=ctx.theme)
