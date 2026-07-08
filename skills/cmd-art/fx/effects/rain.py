"""Matrix-style particle rain (legacy cmd-art effect, framework port)."""
from __future__ import annotations

import random

from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..util import grid_to_str, new_grid


class Rain:
    """Column-droplet simulation. Kept as a class for legacy importers."""

    def __init__(self, width=80, height=40, head=(200, 255, 200), hue=(0, 255, 0),
                 theme=None):
        self.w, self.h = width, height
        self.head = head
        self.hue = hue
        self.theme = theme
        self.drops = [self._spawn() for _ in range(width)]

    def _spawn(self):
        return {"fy": -random.uniform(0, self.h),
                "speed": random.uniform(0.3, 1.1),
                "len": random.randint(4, max(5, self.h // 2))}

    def resize(self, width, height):
        if (width, height) != (self.w, self.h):
            self.w, self.h = width, height
            self.drops = [self._spawn() for _ in range(width)]

    def frame(self, t=None):
        grid = new_grid(self.w, self.h)
        for x, d in enumerate(self.drops):
            d["fy"] += d["speed"]
            head = int(d["fy"])
            for i in range(d["len"]):
                y = head - i
                if 0 <= y < self.h:
                    ch = chr(random.randint(33, 126))
                    if i == 0:
                        grid[y][x] = (ch, self.head)  # bright head
                    else:
                        f = 1.0 - i / d["len"]  # fade toward the tail
                        if self.theme is not None:
                            grid[y][x] = (ch, self.theme.color_at(f * 0.85))
                        else:
                            hr, hg, hb = self.hue
                            grid[y][x] = (ch, (int(hr * f), int(hg * f), int(hb * f)))
            if head - d["len"] > self.h:
                self.drops[x] = self._spawn()
                self.drops[x]["fy"] = 0.0
        return grid_to_str(grid)


@register
class MatrixRain(Effect):
    name = "rain"
    description = "Matrix-style digital rain: bright heads, fading trails."
    tags = ("particles", "classic", "matrix")
    preferred_theme = "matrix-green"
    params = (
        Param("head", "color", None, "hex head color override (default: bright theme)"),
        Param("hue", "color", None, "hex trail color override (default: theme gradient)"),
    )

    def setup(self) -> None:
        self._rain = None

    def render(self, ctx: FrameCtx) -> str:
        head = ctx.params["head"]
        hue = ctx.params["hue"]
        if self._rain is None:
            theme = None if hue is not None else ctx.theme
            self._rain = Rain(ctx.width, ctx.height,
                              head=head or (240, 255, 240),
                              hue=hue or (0, 255, 0), theme=theme)
        self._rain.resize(ctx.width, ctx.height)
        return self._rain.frame(ctx.t)

    def teardown(self) -> None:
        self._rain = None
