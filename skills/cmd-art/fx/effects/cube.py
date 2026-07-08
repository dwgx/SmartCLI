"""Rotating 3D wireframe cube: rotation matrices + perspective + Bresenham edges.

Edges are depth-shaded (near = bright ramp char + bright theme color) and
vertices are marked ``@``. Formulas: research/R2 section 3.
"""
from __future__ import annotations

import math

from ..base import DEFAULT_RAMP, Effect, FrameCtx, Param
from ..registry import register
from ..util import clamp, grid_to_str, new_grid

_VERTS = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
          (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
_EDGES = [(0, 1), (1, 2), (2, 3), (3, 0),
          (4, 5), (5, 6), (6, 7), (7, 4),
          (0, 4), (1, 5), (2, 6), (3, 7)]


def _rotate(v, a, b, c):
    x, y, z = v
    # Rx(a)
    y, z = y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)
    # Ry(b)
    x, z = x * math.cos(b) + z * math.sin(b), -x * math.sin(b) + z * math.cos(b)
    # Rz(c)
    x, y = x * math.cos(c) - y * math.sin(c), x * math.sin(c) + y * math.cos(c)
    return x, y, z


@register
class Cube(Effect):
    name = "cube"
    description = "Rotating wireframe cube (rotation matrices, Bresenham, depth shading)."
    tags = ("3d", "math")
    params = (
        Param("speed", "float", 1.0, "rotation speed multiplier", min=0.0, max=20.0),
        Param("size", "float", 1.0, "cube scale", min=0.2, max=3.0),
        Param("mono", "bool", False, "plain ASCII, no color"),
    )

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        p = ctx.params
        sp = p["speed"]
        a, b, c = ctx.t * 0.9 * sp, ctx.t * 1.2 * sp, ctx.t * 0.6 * sp
        dist = 4.0
        fov = min(w, h * 2) * 0.8
        cx, cy = w / 2.0, h / 2.0
        s = p["size"]

        pts = []
        for v in _VERTS:
            x, y, z = _rotate((v[0] * s, v[1] * s, v[2] * s), a, b, c)
            zv = z + dist
            pts.append((cx + x * fov / zv, cy - y * fov / zv * 0.5, zv))

        grid = new_grid(w, h)
        zmin = dist - s * math.sqrt(3)
        zmax = dist + s * math.sqrt(3)
        theme = ctx.theme
        mono = p["mono"]
        ramp_hi = len(DEFAULT_RAMP) - 1

        def plot(x, y, depth):
            if 0 <= x < w and 0 <= y < h:
                near = clamp(1.0 - (depth - zmin) / (zmax - zmin), 0.0, 1.0)
                ch = DEFAULT_RAMP[max(1, int(near * ramp_hi))]
                color = None if mono else theme.color_at(0.25 + 0.75 * near)
                grid[y][x] = (ch, color)

        for i, j in _EDGES:
            x0, y0, z0 = int(pts[i][0]), int(pts[i][1]), pts[i][2]
            x1, y1, z1 = int(pts[j][0]), int(pts[j][1]), pts[j][2]
            # Bresenham with per-step depth lerp
            dx, sx = abs(x1 - x0), (1 if x0 < x1 else -1)
            dy, sy = -abs(y1 - y0), (1 if y0 < y1 else -1)
            steps = max(dx, -dy, 1)
            err = dx + dy
            n = 0
            x, y = x0, y0
            while True:
                plot(x, y, z0 + (z1 - z0) * (n / steps))
                if x == x1 and y == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    x += sx
                if e2 <= dx:
                    err += dx
                    y += sy
                n += 1
        # vertices on top
        for x, y, z in pts:
            xi, yi = int(x), int(y)
            if 0 <= xi < w and 0 <= yi < h:
                grid[yi][xi] = ("@", None if mono else theme.primary)
        return grid_to_str(grid)
