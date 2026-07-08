"""Typewriter reveal: text appears at chars-per-second with a blinking cursor.

``n = floor(t * cps)`` characters visible; block cursor blinks at ~2 Hz in the
theme accent. Multi-line text supported (\\n in the param).
"""
from __future__ import annotations

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register


@register
class Typewriter(Effect):
    name = "typewriter"
    description = "Character-by-character text reveal with a blinking cursor."
    tags = ("text", "reveal")
    default_fps = 20.0
    params = (
        Param("text", "str", "Hello from SmartCLI.\nThis terminal is alive.",
              "text to type (use \\n for line breaks)"),
        Param("cps", "float", 18.0, "characters per second", min=1.0, max=400.0),
        Param("margin", "int", 2, "left/top margin", min=0, max=20),
    )

    def render(self, ctx: FrameCtx) -> str:
        p = ctx.params
        text = p["text"].replace("\\n", "\n")
        n = int(ctx.t * p["cps"])
        visible = text[:n]
        cursor_on = int(ctx.t * 4) % 2 == 0 and n <= len(text)
        m = p["margin"]
        theme = ctx.theme
        ink = rgb(*theme.primary)
        cur = rgb(*theme.accent)

        rows = [""] * ctx.height
        lines = visible.split("\n")
        for i, line in enumerate(lines):
            y = m // 2 + i
            if 0 <= y < ctx.height:
                s = " " * m + ink + line
                if cursor_on and i == len(lines) - 1:
                    s += cur + "\u258c"
                rows[y] = s + RESET
        return "\n".join(rows)
