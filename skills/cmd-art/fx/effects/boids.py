"""Boids flocking (Craig Reynolds): separation + cohesion + alignment.

Terminal-tuned constants from research/R2 section 12; glyph = heading arrow,
color = per-boid theme gradient slot. Edges wrap (toroidal sky).
"""
from __future__ import annotations

import math
import random

from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..util import clamp, grid_to_str, new_grid

# heading glyphs, 8 sectors starting at "east", screen y points DOWN
_HEADING = [">", "\\", "v", "/", "<", "\\", "^", "/"]

R_SEP, R_NEIGH = 2.0, 8.0
W_SEP, W_COH, W_ALIGN = 1.50, 0.010, 0.125
V_MAX, A_MAX, EPS = 1.0, 0.08, 1e-6


@register
class Boids(Effect):
    name = "boids"
    description = "Reynolds flocking: separation/cohesion/alignment, heading glyphs."
    tags = ("nature", "particles", "simulation")
    default_fps = 24.0
    params = (
        Param("count", "int", 42, "number of boids", min=2, max=400),
        Param("vmax", "float", 1.0, "max speed (cells/frame)", min=0.1, max=4.0),
    )

    def setup(self) -> None:
        self._boids = []
        self._size = None

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        n = ctx.params["count"]
        vmax = ctx.params["vmax"]
        if self._size != (w, h) or len(self._boids) != n:
            self._size = (w, h)
            self._boids = [
                [random.uniform(0, w), random.uniform(0, h),
                 random.uniform(-1, 1), random.uniform(-0.5, 0.5)]
                for _ in range(n)
            ]
        boids = self._boids

        for i, b in enumerate(boids):
            px, py, vx, vy = b
            sep_x = sep_y = 0.0
            coh_x = coh_y = 0.0
            ali_x = ali_y = 0.0
            n_nb = 0
            for j, o in enumerate(boids):
                if i == j:
                    continue
                dx, dy = o[0] - px, o[1] - py
                # wrap-aware shortest offset
                if dx > w / 2: dx -= w
                elif dx < -w / 2: dx += w
                if dy > h / 2: dy -= h
                elif dy < -h / 2: dy += h
                d2 = dx * dx + dy * dy
                if d2 < R_NEIGH * R_NEIGH:
                    n_nb += 1
                    coh_x += px + dx; coh_y += py + dy
                    ali_x += o[2]; ali_y += o[3]
                    if d2 < R_SEP * R_SEP:
                        sep_x -= dx / (d2 + EPS)
                        sep_y -= dy / (d2 + EPS)
            ax = W_SEP * sep_x
            ay = W_SEP * sep_y
            if n_nb:
                ax += W_COH * (coh_x / n_nb - px) + W_ALIGN * (ali_x / n_nb - vx)
                ay += W_COH * (coh_y / n_nb - py) + W_ALIGN * (ali_y / n_nb - vy)
            a = math.hypot(ax, ay)
            if a > A_MAX:
                ax, ay = ax / a * A_MAX, ay / a * A_MAX
            vx += ax; vy += ay
            v = math.hypot(vx, vy)
            lim = vmax if vmax else V_MAX
            if v > lim:
                vx, vy = vx / v * lim, vy / v * lim
            b[0] = (px + vx) % w
            b[1] = (py + vy * 0.6) % h  # aspect: vertical motion looks 2x faster
            b[2], b[3] = vx, vy

        grid = new_grid(w, h)
        theme = ctx.theme
        for i, (px, py, vx, vy) in enumerate(boids):
            x, y = int(px), int(py)
            if 0 <= x < w and 0 <= y < h:
                ang = math.atan2(vy, vx) % (2 * math.pi)
                glyph = _HEADING[int(round(ang / (2 * math.pi) * 8)) % 8]
                grid[y][x] = (glyph, theme.color_at(0.35 + 0.65 * (i / max(1, len(boids) - 1))))
        return grid_to_str(grid)

    def teardown(self) -> None:
        self._boids = []
        self._size = None
