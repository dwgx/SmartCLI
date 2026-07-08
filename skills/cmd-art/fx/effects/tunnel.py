"""3D tunnel fly-through (Lode Vandevenne's precomputed distance/angle tables).

Per cell: distance table ``ratio*texH / r`` and angle table
``0.5*texW*atan2(dy,dx)/pi`` are computed ONCE per (width,height); each frame
only shifts u/v through an XOR-checker texture. Depth fog darkens the far end.
Source: https://lodev.org/cgtutor/tunnel.html (research/R2 section 4).
"""
from __future__ import annotations

import math

from ..base import DEFAULT_RAMP, Effect, FrameCtx, Param
from ..registry import register
from ..util import clamp, grid_to_str, new_grid

TEX = 256  # power of two so & (TEX-1) wraps


@register
class Tunnel(Effect):
    name = "tunnel"
    description = "Demoscene tunnel fly-through (precomputed distance+angle tables)."
    tags = ("3d", "math", "field")
    default_fps = 24.0
    params = (
        Param("speed", "float", 1.0, "fly speed multiplier", min=0.0, max=20.0),
        Param("twist", "float", 1.0, "rotation speed multiplier", min=-10.0, max=10.0),
        Param("mono", "bool", False, "plain ASCII, no color"),
    )

    def setup(self) -> None:
        self._tables = None
        self._size = None

    def _ensure_tables(self, w, h):
        if self._size == (w, h):
            return
        self._size = (w, h)
        cx, cy = w / 2.0, h / 2.0
        dist = [[0] * w for _ in range(h)]
        ang = [[0] * w for _ in range(h)]
        ratio = 24.0
        for y in range(h):
            for x in range(w):
                dx = x - cx
                dy = (y - cy) * 2.0  # aspect: rows are ~2 cells tall
                r = math.hypot(dx, dy)
                if r < 1e-6:
                    r = 1e-6
                dist[y][x] = int(ratio * TEX / r) % TEX
                ang[y][x] = int(0.5 * TEX * math.atan2(dy, dx) / math.pi) % TEX
        self._tables = (dist, ang)

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        self._ensure_tables(w, h)
        dist, ang = self._tables
        p = ctx.params
        shift_d = int(TEX * 1.0 * ctx.t * p["speed"])
        shift_a = int(TEX * 0.25 * ctx.t * p["twist"])
        grid = new_grid(w, h)
        theme = ctx.theme
        mono = p["mono"]
        ramp_hi = len(DEFAULT_RAMP) - 1
        for y in range(h):
            drow, arow = dist[y], ang[y]
            grow = grid[y]
            for x in range(w):
                d = drow[x]
                v = (d + shift_d) & (TEX - 1)
                u = (arow[x] + shift_a) & (TEX - 1)
                checker = ((u >> 4) ^ (v >> 4)) & 1
                depth = clamp(d / (TEX * 0.55), 0.0, 1.0)  # far center -> 1
                bright = (0.95 if checker else 0.45) * (1.0 - depth)
                if bright <= 0.02:
                    continue  # leave the deep center dark
                ch = DEFAULT_RAMP[max(1, int(bright * ramp_hi))]
                color = None if mono else theme.color_at(bright)
                grow[x] = (ch, color)
        return grid_to_str(grid)

    def teardown(self) -> None:
        self._tables = None
        self._size = None
