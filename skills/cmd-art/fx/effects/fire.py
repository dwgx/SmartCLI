"""Demoscene fire: bottom-seeded heat buffer with upward cooling propagation.

Lode Vandevenne's exact kernel: each cell = (4 neighbours below) * 32 / 129
(the /129 is the cooling). Heat 0..255 maps through the ramp + theme gradient.
Source: https://lodev.org/cgtutor/fire.html (research/R2 section 7).
"""
from __future__ import annotations

import random

from ..base import DEFAULT_RAMP, Effect, FrameCtx, Param
from ..registry import register
from ..util import grid_to_str, new_grid


@register
class Fire(Effect):
    name = "fire"
    description = "Classic demoscene fire (heat buffer, cooling kernel, palette ramp)."
    tags = ("nature", "classic", "field")
    preferred_theme = "fire"
    default_fps = 24.0
    params = (
        Param("cool", "int", 0, "extra cooling 0..8 (taller/shorter flames)",
              min=0, max=8),
        Param("mono", "bool", False, "plain ASCII, no color"),
    )

    def setup(self) -> None:
        self._buf = None
        self._size = None

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        rows = h + 2  # two hidden seed rows below the visible area
        if self._size != (w, h):
            self._size = (w, h)
            self._buf = [[0] * w for _ in range(rows)]
        buf = self._buf
        cool = ctx.params["cool"]

        # seed the two bottom (hidden) rows with random heat
        for y in (rows - 1, rows - 2):
            brow = buf[y]
            for x in range(w):
                brow[x] = random.randint(0, 255)

        # propagate upward: Lode's kernel sum*32//129, minus optional extra cool
        for y in range(rows - 3, -1, -1):
            row = buf[y]
            b1 = buf[y + 1]
            b2 = buf[y + 2]
            for x in range(w):
                s = (b1[x - 1] if x > 0 else b1[w - 1]) + b1[x] \
                    + (b1[x + 1] if x < w - 1 else b1[0]) + b2[x]
                v = (s * 32) // 129 - cool
                row[x] = v if v > 0 else 0

        grid = new_grid(w, h)
        theme = ctx.theme
        mono = ctx.params["mono"]
        ramp_n = len(DEFAULT_RAMP)
        for y in range(h):
            brow = buf[y]
            grow = grid[y]
            for x in range(w):
                heat = brow[x]
                if heat < 8:
                    continue
                ch = DEFAULT_RAMP[min(ramp_n - 1, heat * ramp_n // 256)]
                color = None if mono else theme.color_at(heat / 255.0)
                grow[x] = (ch, color)
        return grid_to_str(grid)

    def teardown(self) -> None:
        self._buf = None
        self._size = None
