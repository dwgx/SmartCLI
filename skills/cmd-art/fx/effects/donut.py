"""The classic spinning ASCII donut (Andy Sloane's donut.c math).

Torus: tube radius R1=1 revolved at distance R2=2, viewer at K2=5, projection
scale K1 derived from screen width. Luminance = surface normal . light(0,1,-1),
z-buffered with ooz=1/z (bigger wins). Ramp: ``.,-~:;=!*#$@`` (12 chars).
Source: https://www.a1k0n.net/2011/07/20/donut-math.html (see research/R2).
"""
from __future__ import annotations

import math

from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..util import clamp, grid_to_str, new_grid

DONUT_RAMP = ".,-~:;=!*#$@"
SQRT2 = math.sqrt(2.0)


@register
class Donut(Effect):
    name = "donut"
    description = "THE spinning ASCII torus (Andy Sloane donut.c: z-buffer + N.L shading)."
    tags = ("3d", "math", "classic")
    params = (
        Param("speed", "float", 1.0, "spin speed multiplier", min=0.0, max=20.0),
        Param("r1", "float", 1.0, "tube radius", min=0.2, max=4.0),
        Param("r2", "float", 2.0, "torus radius", min=0.5, max=8.0),
        Param("mono", "bool", False, "plain ASCII, no color"),
    )

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        p = ctx.params
        R1, R2, K2 = p["r1"], p["r2"], 5.0
        # Projection scale: fill ~3/4 of the smaller axis (height counts double:
        # terminal cells are ~2x taller than wide).
        K1 = min(w, h * 2) * K2 * 3.0 / (8.0 * (R1 + R2))
        A = ctx.t * 1.2 * p["speed"]   # ~= donut.c A += 0.04/frame @30fps
        B = ctx.t * 0.6 * p["speed"]   # ~= donut.c B += 0.02/frame @30fps
        cA, sA, cB, sB = math.cos(A), math.sin(A), math.cos(B), math.sin(B)

        grid = new_grid(w, h)
        zbuf = [[0.0] * w for _ in range(h)]
        cx, cy = w / 2.0, h / 2.0
        mono = p["mono"]
        theme = ctx.theme
        ramp_n = len(DONUT_RAMP)

        theta = 0.0
        while theta < 2 * math.pi:          # around the tube cross-section
            ct, st = math.cos(theta), math.sin(theta)
            circlex = R2 + R1 * ct
            circley = R1 * st
            phi = 0.0
            while phi < 2 * math.pi:        # revolve around the torus axis
                cp, sp = math.cos(phi), math.sin(phi)
                # world coords after Rx(A) then Rz(B) (donut.c form)
                x = circlex * (cB * cp + sA * sB * sp) - circley * cA * sB
                y = circlex * (sB * cp - sA * cB * sp) + circley * cA * cB
                z = K2 + cA * circlex * sp + circley * sA
                ooz = 1.0 / z
                xp = int(cx + K1 * ooz * x)
                yp = int(cy - K1 * ooz * y * 0.5)  # aspect: cells ~2x tall
                if 0 <= xp < w and 0 <= yp < h and ooz > zbuf[yp][xp]:
                    # luminance: rotated surface normal . light (0,1,-1)
                    L = (cp * ct * sB - cA * ct * sp - sA * st
                         + cB * (cA * st - ct * sA * sp))
                    if L > 0.0:
                        zbuf[yp][xp] = ooz
                        li = clamp(int(L * 8.0), 0, ramp_n - 1)
                        color = None if mono else theme.color_at(
                            clamp(L / SQRT2, 0.0, 1.0))
                        grid[yp][xp] = (DONUT_RAMP[li], color)
                phi += 0.02
            theta += 0.07
        return grid_to_str(grid)
