"""Sparkle/shimmer: dim centered text with short-lived bright glints on top.

Each frame spawns a few random sparkles with a TTL; brightness lerps from
theme.primary toward white and dies out. Source: research/R1 part D.6.
"""
from __future__ import annotations

import random

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..theme import lerp_color
from ..util import grid_to_str, new_grid

SPARK_CHARS = "*+.\u00b7"


@register
class Sparkle(Effect):
    name = "sparkle"
    description = "Dim text under a field of short-lived bright glints."
    tags = ("text", "particles")
    default_fps = 20.0
    params = (
        Param("text", "str", "* S P A R K L E *", "centered text (empty for none)"),
        Param("density", "float", 1.0, "sparkle spawn multiplier", min=0.0, max=8.0),
    )

    def setup(self) -> None:
        self._sparks = {}  # (x, y) -> [ttl, max_ttl, char]

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        theme = ctx.theme
        grid = new_grid(w, h)

        # dim base text, centered
        text = ctx.params["text"]
        if text:
            y = h // 2
            x0 = max(0, (w - len(text)) // 2)
            dim = theme.color_at(0.35)
            for i, ch in enumerate(text):
                if ch != " " and 0 <= x0 + i < w:
                    grid[y][x0 + i] = (ch, dim)

        # spawn sparkles
        spawn = max(1, int(w * h / 220 * ctx.params["density"]))
        for _ in range(spawn):
            x, y = random.randrange(w), random.randrange(h)
            if (x, y) not in self._sparks:
                ttl = random.randint(3, 10)
                self._sparks[(x, y)] = [ttl, ttl, random.choice(SPARK_CHARS)]

        # age + draw sparkles
        dead = []
        for (x, y), s in self._sparks.items():
            s[0] -= 1
            if s[0] <= 0:
                dead.append((x, y))
                continue
            a = s[0] / s[1]
            grid[y % h][x % w] = (s[2], lerp_color(theme.primary, (255, 255, 255), a))
        for k in dead:
            del self._sparks[k]
        return grid_to_str(grid)

    def teardown(self) -> None:
        self._sparks = {}
