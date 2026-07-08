"""Perspective starfield fly-through: project (x,y)/z, respawn at far plane.

Brightness rises as stars approach (1 - z/maxZ) through '' .+*#@''-style ramp.
Source: research/R2 section 5.
"""
from __future__ import annotations

import random

from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..util import clamp, grid_to_str, new_grid

STAR_RAMP = ".+*#@"


@register
class Starfield(Effect):
    name = "starfield"
    description = "Perspective starfield warp (1/z projection, depth brightness)."
    tags = ("3d", "particles", "space")
    params = (
        Param("speed", "float", 1.0, "fly speed multiplier", min=0.0, max=20.0),
        Param("density", "float", 1.0, "star count multiplier", min=0.1, max=5.0),
    )

    def setup(self) -> None:
        self._stars = []
        self._last_t = None
        self._size = None

    def _spawn(self, z=None):
        return [random.uniform(-1.0, 1.0), random.uniform(-1.0, 1.0),
                z if z is not None else random.uniform(0.05, 1.0)]

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        n = max(8, int(w * h / 14 * ctx.params["density"]))
        if self._size != (w, h) or len(self._stars) != n:
            self._size = (w, h)
            self._stars = [self._spawn() for _ in range(n)]
        dt = 0.0 if self._last_t is None else clamp(ctx.t - self._last_t, 0.0, 0.2)
        self._last_t = ctx.t

        cx, cy = w / 2.0, h / 2.0
        focal = 0.35
        grid = new_grid(w, h)
        theme = ctx.theme
        fall = 0.55 * ctx.params["speed"]
        for s in self._stars:
            s[2] -= fall * dt
            if s[2] <= 0.02:
                s[0], s[1], s[2] = self._spawn(z=1.0)
            k = focal / s[2]
            sx = int(cx + s[0] * k * w * 0.5)
            sy = int(cy + s[1] * k * h * 0.5)
            if 0 <= sx < w and 0 <= sy < h:
                bright = clamp(1.0 - s[2], 0.0, 1.0)
                ch = STAR_RAMP[int(bright * (len(STAR_RAMP) - 1))]
                grid[sy][sx] = (ch, theme.color_at(0.15 + 0.85 * bright))
        return grid_to_str(grid)

    def teardown(self) -> None:
        self._stars = []
        self._last_t = None
