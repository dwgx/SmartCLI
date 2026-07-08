"""Fireworks: shells rise, explode into radial sparks under gravity, fade out.

Semi-implicit Euler integration (v += g*dt; p += v*dt), age->brightness fade.
Terminal y points down so gravity is positive. Source: research/R2 section 13.
"""
from __future__ import annotations

import math
import random

from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..util import clamp, grid_to_str, new_grid

SPARK_RAMP = ".:*#@"
G = 14.0  # cells / s^2 (screen rows; visually ~2x because rows are tall)


@register
class Fireworks(Effect):
    name = "fireworks"
    description = "Rising shells exploding into gravity-bound colored sparks."
    tags = ("particles", "celebration")
    params = (
        Param("rate", "float", 0.9, "average launches per second", min=0.05, max=10.0),
        Param("sparks", "int", 36, "sparks per burst", min=6, max=200),
    )

    def setup(self) -> None:
        self._shells = []   # rising: [x, y, vy, fuse_y, color_u]
        self._sparks = []   # [x, y, vx, vy, age, life, color_u]
        self._last_t = None

    def _launch(self, w: int, h: int) -> None:
        x = random.uniform(w * 0.15, w * 0.85)
        self._shells.append([x, float(h - 1), -random.uniform(h * 0.55, h * 0.8),
                             random.uniform(h * 0.15, h * 0.45),
                             random.random()])

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        p = ctx.params
        first = self._last_t is None
        dt = 0.0 if first else clamp(ctx.t - self._last_t, 0.0, 0.2)
        self._last_t = ctx.t
        theme = ctx.theme

        # Guarantee immediate activity: one shell on the very first frame so a
        # bounded short render always shows a (colored) rising shell instead of a
        # blank screen while waiting on the Poisson launcher below.
        if first:
            self._launch(w, h)
        # launch new shells (Poisson-ish)
        if dt > 0 and random.random() < p["rate"] * dt:
            self._launch(w, h)

        # advance shells; explode at fuse height (or when slowed to a stop)
        keep = []
        for s in self._shells:
            s[2] += G * dt * 0.5    # shells decelerate half as fast (drag-ish)
            s[1] += s[2] * dt
            if s[1] <= s[3] or s[2] >= -1.0:
                n = p["sparks"]
                for k in range(n):
                    ang = 2 * math.pi * k / n + random.uniform(-0.1, 0.1)
                    speed = random.uniform(3.0, 11.0)
                    self._sparks.append([
                        s[0], s[1],
                        math.cos(ang) * speed,
                        math.sin(ang) * speed * 0.5,  # aspect squash
                        0.0, random.uniform(0.7, 1.6), s[4]])
            else:
                keep.append(s)
        self._shells = keep

        # advance sparks
        alive = []
        for q in self._sparks:
            q[3] += G * dt
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[4] += dt
            if q[4] < q[5] and 0 <= q[1] < h + 2:
                alive.append(q)
        self._sparks = alive

        grid = new_grid(w, h)
        for x, y, vx, vy, age, life, cu in self._sparks:
            xi, yi = int(x), int(y)
            if 0 <= xi < w and 0 <= yi < h:
                bright = clamp(1.0 - age / life, 0.0, 1.0)
                ch = SPARK_RAMP[int(bright * (len(SPARK_RAMP) - 1))]
                base = theme.cycle(cu) if theme.hsv else theme.color_at(0.3 + 0.7 * cu)
                grid[yi][xi] = (ch, (int(base[0] * bright),
                                     int(base[1] * bright),
                                     int(base[2] * bright)))
        for x, y, vy, fy, cu in self._shells:
            xi, yi = int(x), int(y)
            if 0 <= xi < w and 0 <= yi < h:
                grid[yi][xi] = ("|", theme.primary)
        return grid_to_str(grid)

    def teardown(self) -> None:
        self._shells = []
        self._sparks = []
        self._last_t = None
