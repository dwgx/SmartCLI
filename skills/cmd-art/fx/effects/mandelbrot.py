"""Mandelbrot set — animated infinite zoom (knowledge -> effect).

Implements [[mandelbrot]] from the knowledge graph: for each cell iterate
z = z^2 + c from z0=0 with c = the cell's complex coordinate; the escape count
picks the color. Animated by zooming toward a fixed interesting point on the
boundary, so the reel is an endless dive into the fractal.

Pure frame producer: (t, w, h) -> one frame string. No I/O, no ANSI modes.
"""
from __future__ import annotations

import colorsys
import math

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register

MAX_ITER = 90
_LOG2 = math.log(2.0)
# A classic zoom target on the boundary (Seahorse Valley edge).
TARGET_X, TARGET_Y = -0.743643887037, 0.131825904205


def _mandel_frame(t, width, height, palette, theme, speed):
    # Zoom in exponentially over time (loops the "dive" feel without an end).
    zoom = 0.9 * math.exp(0.28 * speed * (t % 22.0))   # reset every 22s
    span_x = 3.0 / zoom
    span_y = span_x * (height * 2.0) / width if width else 3.0 / zoom
    lines = []
    for row in range(height):
        y0 = TARGET_Y + (row / max(1, height - 1) - 0.5) * span_y
        out = []
        last = None
        for col in range(width):
            x0 = TARGET_X + (col / max(1, width - 1) - 0.5) * span_x
            x = y = 0.0
            i = 0
            m2 = 0.0
            while m2 <= 256.0 and i < MAX_ITER:   # large bailout for smooth term
                xt = x * x - y * y + x0
                y = 2.0 * x * y + y0
                x = xt
                m2 = x * x + y * y
                i += 1
            if i >= MAX_ITER:
                c = (0, 0, 0)                        # inside -> black
            else:
                # Continuous iteration count -> no concentric banding.
                nu = math.log(math.log(m2) * 0.5) / _LOG2
                n = (i + 1 - nu) / MAX_ITER
                n = 0.0 if n < 0 else (1.0 if n > 1 else n)
                if palette == "rgb":
                    rf, gf, bf = colorsys.hsv_to_rgb(n, 1.0, 1.0)
                    c = (int(rf * 255), int(gf * 255), int(bf * 255))
                elif palette == "theme" and theme is not None:
                    c = theme.cycle(n) if theme.hsv else theme.color_at(n)
                else:
                    rf, gf, bf = colorsys.hsv_to_rgb((n + t * 0.03) % 1.0, 0.85, 1.0)
                    c = (int(rf * 255), int(gf * 255), int(bf * 255))
            if c != last:
                out.append(rgb(*c, bg=True))
                last = c
            out.append(" ")
        lines.append("".join(out) + RESET)
    return "\n".join(lines)


@register
class Mandelbrot(Effect):
    name = "mandelbrot"
    aliases = ("mandel",)
    description = "Animated infinite zoom into the Mandelbrot set (escape-time)."
    tags = ("field", "fractal", "math")
    preferred_theme = "viridis"
    default_fps = 20.0
    params = (
        Param("palette", "str", "theme", "color source", choices=("theme", "hsv", "rgb")),
        Param("speed", "float", 1.0, "zoom speed", min=0.1, max=4.0),
    )

    def render(self, ctx: FrameCtx) -> str:
        return _mandel_frame(ctx.t, ctx.width, ctx.height,
                             ctx.params["palette"], ctx.theme, ctx.params["speed"])
