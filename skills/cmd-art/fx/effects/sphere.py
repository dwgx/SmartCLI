"""Rotating Lambert-shaded 3D sphere (legacy cmd-art effect, framework port)."""
from __future__ import annotations

import math

from ..base import DEFAULT_RAMP, Effect, FrameCtx, Param
from ..registry import register
from ..util import grid_to_str, new_grid


def sphere_frame(A, B, width=60, height=30, R=1.0, D=4.0, color=False,
                 tint=(80, 220, 200), theme=None):
    """One sphere frame. Kept as a function for legacy importers.

    ``theme`` (when given and ``tint`` is None) shades via ``theme.color_at``;
    otherwise the legacy luminance-scaled ``tint`` is used. ``color=False``
    renders the plain ASCII ramp.
    """
    grid = new_grid(width, height)
    zbuf = [[0.0] * width for _ in range(height)]  # 0 = infinitely far
    cx, cy = width / 2.0, height / 2.0
    K = width * D / (4.0 * R)
    ASPECT = 0.5  # cells ~2x taller than wide -> compress vertical for roundness
    lx, ly, lz = 0.0, 0.707, -0.707  # light: front + slightly up
    ca, sa, cb, sb = math.cos(A), math.sin(A), math.cos(B), math.sin(B)
    ramp_max = len(DEFAULT_RAMP) - 1
    u = 0.0
    two_pi = 2 * math.pi
    while u < two_pi:
        cu, su = math.cos(u), math.sin(u)
        v = 0.0
        while v < math.pi:
            sv, cv = math.sin(v), math.cos(v)
            x, y, z = sv * cu, sv * su, cv  # point == normal (unit sphere)
            # Rx(A)
            y1, z1 = y * ca - z * sa, y * sa + z * ca
            x1 = x
            # Ry(B)
            x2, z2 = x1 * cb + z1 * sb, -x1 * sb + z1 * cb
            y2 = y1
            zc = z2 * R + D
            inv = 1.0 / zc
            sx = int(cx + K * (x2 * R) * inv)
            sy = int(cy - K * (y2 * R) * inv * ASPECT)
            if 0 <= sx < width and 0 <= sy < height and inv > zbuf[sy][sx]:
                lum = x2 * lx + y2 * ly + z2 * lz  # rotated normal . light
                if lum < 0.0:
                    lum = 0.0
                zbuf[sy][sx] = inv
                ch = DEFAULT_RAMP[int(lum * ramp_max)]
                if not color:
                    c = None
                elif tint is not None:
                    c = (int(tint[0] * lum), int(tint[1] * lum), int(tint[2] * lum))
                else:
                    c = theme.color_at(lum)
                grid[sy][sx] = (ch, c)
            v += 0.04
        u += 0.07
    return grid_to_str(grid)


@register
class Sphere(Effect):
    name = "sphere"
    description = "Rotating Lambert-shaded 3D ball (z-buffer + ASCII luminance ramp)."
    tags = ("3d", "math", "classic")
    params = (
        Param("speed", "float", 1.0, "rotation speed multiplier", min=0.0, max=20.0),
        Param("mono", "bool", False, "plain ASCII ramp, no color"),
        Param("tint", "color", None, "hex tint override (legacy); empty = theme shading"),
    )

    def render(self, ctx: FrameCtx) -> str:
        p = ctx.params
        sp = p["speed"]
        return sphere_frame(A=ctx.t * 0.9 * sp, B=ctx.t * 1.3 * sp,
                            width=ctx.width, height=ctx.height,
                            color=not p["mono"], tint=p["tint"], theme=ctx.theme)
