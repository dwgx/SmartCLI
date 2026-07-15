"""Julia set — animated escape-time fractal (knowledge -> effect).

Implements [[julia-set]] from the knowledge graph: the same z = z^2 + c
escape-time iteration as Mandelbrot, but c is a constant and z0 is the pixel.
Animated by walking c around a small loop, so the fractal morphs continuously.
Rendered as truecolor BACKGROUND cells (whole screen is the canvas), colored by
escape count via the active theme.

Pure frame producer: (t, w, h) -> one frame string. No I/O, no ANSI modes.
"""
from __future__ import annotations

import colorsys
import math

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register

MAX_ITER = 80          # escape cap (kept modest — a full screen of pixels/frame)
ESCAPE_R2 = 4.0        # |z|^2 > 4 means escaped


def _julia_frame(t, width, height, palette, theme, speed):
    # c walks a Lissajous loop through the interesting region so the set morphs.
    ang = t * 0.35 * speed
    cx = 0.7885 * math.cos(ang)          # classic |c|=0.7885 circle -> rich shapes
    cy = 0.7885 * math.sin(ang)
    # Map screen cells to the complex plane. Account for cell aspect (~2:1) so the
    # fractal isn't vertically squashed: widen the imaginary span per row.
    span_x = 3.0
    span_y = 3.0 * (height * 2.0) / width if width else 3.0
    lines = []
    for row in range(height):
        zy0 = (row / max(1, height - 1) - 0.5) * span_y
        out = []
        last = None
        for col in range(width):
            zx = (col / max(1, width - 1) - 0.5) * span_x
            zy = zy0
            i = 0
            while zx * zx + zy * zy <= ESCAPE_R2 and i < MAX_ITER:
                xt = zx * zx - zy * zy + cx
                zy = 2.0 * zx * zy + cy
                zx = xt
                i += 1
            if i >= MAX_ITER:
                c = (0, 0, 0)                      # inside the set -> black
            else:
                n = i / MAX_ITER                   # escape ratio -> color
                if palette == "rgb":
                    rf, gf, bf = colorsys.hsv_to_rgb(n, 1.0, 1.0)
                    c = (int(rf * 255), int(gf * 255), int(bf * 255))
                elif palette == "theme" and theme is not None:
                    c = theme.cycle(n) if theme.hsv else theme.color_at(n)
                else:
                    rf, gf, bf = colorsys.hsv_to_rgb((n + t * 0.05) % 1.0, 0.9, 1.0)
                    c = (int(rf * 255), int(gf * 255), int(bf * 255))
            if c != last:
                out.append(rgb(*c, bg=True))
                last = c
            out.append(" ")
        lines.append("".join(out) + RESET)
    return "\n".join(lines)


@register
class Julia(Effect):
    name = "julia"
    aliases = ("juliaset",)
    description = "Animated Julia-set fractal (escape-time z^2+c, morphing c)."
    tags = ("field", "fractal", "math")
    preferred_theme = "viridis"
    default_fps = 20.0
    params = (
        Param("palette", "str", "theme", "color source", choices=("theme", "hsv", "rgb")),
        Param("speed", "float", 1.0, "how fast c walks its loop", min=0.0, max=8.0),
    )

    def render(self, ctx: FrameCtx) -> str:
        return _julia_frame(ctx.t, ctx.width, ctx.height,
                            ctx.params["palette"], ctx.theme, ctx.params["speed"])
