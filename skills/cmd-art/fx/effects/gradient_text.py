"""lolcat-style gradient text: per-char color drift along lines, animated.

HSV themes use the classic three-sine lolcat rainbow; gradient themes sweep
their multi-stop palette. ``big=true`` pipes the text through figlet first.
Formula source: research/R1 part B (lolcat lol.rb).
"""
from __future__ import annotations

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..theme import lolcat_color
from .text3d import big_text


@register
class GradientText(Effect):
    name = "gradient_text"
    aliases = ("lolcat",)
    description = "lolcat rainbow / theme-gradient text, drifting over time."
    tags = ("text", "color")
    preferred_theme = "rainbow"
    default_fps = 20.0
    params = (
        Param("text", "str", "Taste the rainbow, straight from stdlib.",
              "text to colorize (use \\n for line breaks)"),
        Param("big", "bool", False, "render through figlet/block font first"),
        Param("freq", "float", 0.25, "color frequency along a line", min=0.01, max=3.0),
        Param("spread", "float", 3.0, "chars per color step", min=0.5, max=20.0),
        Param("drift", "float", 8.0, "animation drift speed", min=0.0, max=100.0),
    )

    @classmethod
    def is_animated(cls, params: dict) -> bool:
        return params.get("drift", 8.0) > 0

    def setup(self) -> None:
        self._big_cache = None
        self._key = None

    def _lines(self, p):
        text = p["text"].replace("\\n", "\n")
        if not p["big"]:
            return text.split("\n")
        key = (text,)
        if self._key != key:
            out = []
            for chunk in text.split("\n"):
                out.extend(big_text(chunk))
            self._big_cache, self._key = out, key
        return self._big_cache

    def render(self, ctx: FrameCtx) -> str:
        p = ctx.params
        lines = self._lines(p)
        theme = ctx.theme
        offset = ctx.t * p["drift"]
        rows = []
        for y, line in enumerate(lines[:ctx.height]):
            buf, last = [], None
            for x, ch in enumerate(line[:ctx.width]):
                if ch == " ":
                    buf.append(" ")
                    continue
                i = offset + y * 2 + x / p["spread"]
                if theme.hsv:
                    c = lolcat_color(i, freq=p["freq"] * 2.0, spread=1.0)
                else:
                    c = theme.color_at((i * p["freq"] * 0.25) % 1.0)
                if c != last:
                    buf.append(rgb(*c))
                    last = c
                buf.append(ch)
            buf.append(RESET)
            rows.append("".join(buf))
        rows.extend([""] * (ctx.height - len(rows)))
        return "\n".join(rows)
