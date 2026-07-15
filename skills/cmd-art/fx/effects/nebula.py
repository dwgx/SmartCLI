"""Nebula — domain-warped noise field with filaments and stars (knowledge -> effect).

The richest of the noise-composition fields. A domain-warped fBm gives flowing
gas filaments; its intermediate warp field q drives multi-color mixing (deep
violet / magenta / cyan); ridged noise adds bright compressed filaments; a
sparse high-frequency layer sprinkles foreground stars. See _noiselib and IQ's
domain-warping article.

Pure frame producer: (t, w, h) -> one frame string. No I/O, no ANSI modes.
"""
from __future__ import annotations

import math

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register
from .._noiselib import domain_warp, ridged


def _mix(c0, c1, u):
    u = 0.0 if u < 0 else (1.0 if u > 1 else u)
    return (int(c0[0] + (c1[0] - c0[0]) * u),
            int(c0[1] + (c1[1] - c0[1]) * u),
            int(c0[2] + (c1[2] - c0[2]) * u))


# Deep-space palette stops: near-black -> violet -> magenta -> cyan-white.
_C_BG = (6, 4, 18)
_C_VIOLET = (60, 20, 120)
_C_MAGENTA = (170, 40, 150)
_C_CYAN = (120, 210, 230)


def _nebula_frame(t, width, height, speed, use_theme, theme):
    tt = t * 0.06 * speed          # nebulae churn slowly
    lines = []
    for row in range(height):
        ny = row * 0.11 * 2.0      # ×2 for cell aspect
        out = []
        last = None
        for col in range(width):
            nx = col * 0.11
            f, qx, qy = domain_warp(nx, ny, tt)
            dens = (f + 1.0) * 0.5                 # gas density -> [0,1]
            dens = 0.0 if dens < 0 else (1.0 if dens > 1 else dens)  # warp can overshoot
            qmag = min(1.0, math.hypot(qx, qy))    # warp magnitude -> color mix
            if use_theme and theme is not None:
                c = theme.color_at(min(1.0, dens * 0.6 + qmag * 0.4))
                c = _mix(_C_BG, c, dens ** 1.4)
            else:
                # base violet->magenta by density, blend toward cyan by warp mag
                base = _mix(_C_VIOLET, _C_MAGENTA, dens)
                base = _mix(base, _C_CYAN, qmag * 0.7)
                c = _mix(_C_BG, base, dens ** 1.4)   # fade thin gas to near-black
            # bright compressed filaments
            rg = ridged(nx * 1.7 + 3.0, ny * 1.7, tt)
            if rg > 0.86:
                boost = (rg - 0.86) / 0.14
                c = _mix(c, (230, 240, 255), boost * 0.7)
            # sparse foreground stars (deterministic hash -> stable, no flicker)
            hsh = (col * 73856093) ^ (row * 19349663)
            if (hsh & 1023) < 4 and dens < 0.6:
                c = (245, 245, 255)
            if c != last:
                out.append(rgb(*c, bg=True))
                last = c
            out.append(" ")
        lines.append("".join(out) + RESET)
    return "\n".join(lines)


@register
class Nebula(Effect):
    name = "nebula"
    aliases = ("galaxy", "cosmos")
    description = "Domain-warped gas nebula: flowing filaments, multi-color mix, stars."
    tags = ("field", "space", "noise")
    preferred_theme = "synthwave"
    default_fps = 20.0
    params = (
        Param("speed", "float", 1.0, "how fast the nebula churns", min=0.1, max=4.0),
        Param("palette", "str", "cosmic", "color source", choices=("cosmic", "theme")),
    )

    def render(self, ctx: FrameCtx) -> str:
        return _nebula_frame(ctx.t, ctx.width, ctx.height, ctx.params["speed"],
                             ctx.params["palette"] == "theme", ctx.theme)
