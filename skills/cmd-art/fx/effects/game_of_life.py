"""Conway's Game of Life (B3/S23) on a toroidal grid, age-colored.

Newborn cells glow at the bright end of the theme; long-lived cells settle
toward the base color. Auto-reseeds when the population collapses.
Source: research/R2 section 8.
"""
from __future__ import annotations

import random

from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..util import clamp, grid_to_str, new_grid


@register
class GameOfLife(Effect):
    name = "life"
    aliases = ("game_of_life",)
    description = "Conway's Game of Life, toroidal wrap, age-based theme colors."
    tags = ("nature", "automata", "classic")
    default_fps = 12.0
    params = (
        Param("fill", "float", 0.22, "initial alive fraction", min=0.01, max=0.9),
        Param("char", "str", "#", "glyph for a live cell"),
        Param("seed", "int", 0, "RNG seed (0 = random)"),
    )

    def setup(self) -> None:
        self._cells = None
        self._age = None
        self._size = None

    def _reseed(self, w, h, fill, rng):
        self._cells = [[1 if rng.random() < fill else 0 for _ in range(w)]
                       for _ in range(h)]
        self._age = [[0] * w for _ in range(h)]

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        p = ctx.params
        if self._size != (w, h):
            self._size = (w, h)
            rng = random.Random(p["seed"] or None)
            self._reseed(w, h, p["fill"], rng)

        cells, age = self._cells, self._age
        nxt = [[0] * w for _ in range(h)]
        pop = 0
        for y in range(h):
            ym, yp = (y - 1) % h, (y + 1) % h
            for x in range(w):
                xm, xp = (x - 1) % w, (x + 1) % w
                n = (cells[ym][xm] + cells[ym][x] + cells[ym][xp]
                     + cells[y][xm] + cells[y][xp]
                     + cells[yp][xm] + cells[yp][x] + cells[yp][xp])
                alive = 1 if (n == 3 or (cells[y][x] and n == 2)) else 0
                nxt[y][x] = alive
                if alive:
                    pop += 1
                    age[y][x] = age[y][x] + 1 if cells[y][x] else 1
                else:
                    age[y][x] = 0
        self._cells = nxt
        if pop < max(4, (w * h) // 200):  # died out / nearly static -> reseed
            self._reseed(w, h, p["fill"], random.Random())

        grid = new_grid(w, h)
        theme = ctx.theme
        ch = (p["char"] or "#")[0]
        for y in range(h):
            crow, arow, grow = self._cells[y], age[y], grid[y]
            for x in range(w):
                if crow[x]:
                    # young = bright end, old = settled base tones
                    a = clamp(arow[x] / 14.0, 0.0, 1.0)
                    grow[x] = (ch, theme.color_at(1.0 - 0.75 * a))
        return grid_to_str(grid)

    def teardown(self) -> None:
        self._cells = None
        self._age = None
        self._size = None
