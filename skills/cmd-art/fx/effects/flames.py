"""Flames — noise-convection fire (knowledge -> effect).

A different fire from the cellular `fire` effect: this treats flame as rising
heat convection. A domain-warped fBm temperature field scrolls upward, is damped
by a vertical gradient (cooler toward the top), swayed by a small horizontal
wobble, and colored through the physical black-body ramp. See _noiselib.

Pure frame producer: (t, w, h) -> one frame string. No I/O, no ANSI modes.
"""
from __future__ import annotations

import math

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register
from .._noiselib import domain_warp, black_body


def _flames_frame(t, width, height, speed, theme, use_theme):
    lines = []
    for row in range(height):
        # vertical position 0 (top) .. 1 (bottom); heat rises so bottom is hot.
        vy = row / max(1, height - 1)
        damp = vy * vy               # strong falloff toward the top -> flame tips
        out = []
        last = None
        for col in range(width):
            nx = col * 0.08 + 0.3 * math.sin(t * 1.3 + vy * 3.0)  # wobble/sway
            ny = vy * 1.6 - t * speed * 0.9                       # scroll upward
            f, _q, _r = domain_warp(nx, ny, t * 0.15)
            base = (f + 1.0) * 0.5
            base = 0.0 if base < 0 else (1.0 if base > 1 else base)  # warp overshoot
            temp = base * damp                                   # [0,1] × falloff
            if temp < 0.14:
                c = (0, 0, 0)                                    # below flame -> dark
            elif use_theme and theme is not None:
                c = theme.color_at(min(1.0, temp * 1.3))
            else:
                c = black_body(1200 + temp * 5200)               # physical fire ramp
            if c != last:
                out.append(rgb(*c, bg=True))
                last = c
            out.append(" ")
        lines.append("".join(out) + RESET)
    return "\n".join(lines)


@register
class Flames(Effect):
    name = "flames"
    aliases = ("firefield", "bonfire")
    description = "Noise-convection fire: rising domain-warped heat, black-body color."
    tags = ("field", "fire", "noise")
    preferred_theme = "fire"
    default_fps = 24.0
    params = (
        Param("speed", "float", 1.0, "how fast the flame rises", min=0.1, max=4.0),
        Param("palette", "str", "blackbody", "color source",
              choices=("blackbody", "theme")),
    )

    def render(self, ctx: FrameCtx) -> str:
        return _flames_frame(ctx.t, ctx.width, ctx.height, ctx.params["speed"],
                             ctx.theme, ctx.params["palette"] == "theme")
