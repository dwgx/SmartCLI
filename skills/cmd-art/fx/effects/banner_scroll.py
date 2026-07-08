"""Marquee: a big figlet/block banner scrolling across the screen with a
drifting theme gradient (per-column color = theme.color_at / theme.cycle)."""
from __future__ import annotations

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register
from .text3d import big_text


@register
class BannerScroll(Effect):
    name = "banner_scroll"
    aliases = ("marquee",)
    description = "Scrolling figlet banner with a drifting theme gradient."
    tags = ("text", "banner")
    params = (
        Param("text", "str", "SMARTCLI", "banner text"),
        Param("font", "str", "standard", "pyfiglet font (fallback: block font)"),
        Param("speed", "float", 24.0, "scroll speed in columns/second", min=1.0, max=200.0),
        Param("gap", "int", 12, "blank columns between repeats", min=0, max=200),
    )

    def setup(self) -> None:
        self._lines = None
        self._key = None

    def _banner(self, p):
        key = (p["text"], p["font"], p["gap"])
        if self._key != key:
            lines = big_text(p["text"], p["font"])
            width = max(len(l) for l in lines) + p["gap"]
            self._lines = [l.ljust(width) for l in lines]
            self._key = key
        return self._lines

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        p = ctx.params
        lines = self._banner(p)
        bw = len(lines[0])
        offset = int(ctx.t * p["speed"]) % bw
        top = max(0, (h - len(lines)) // 2)
        theme = ctx.theme
        period = max(24.0, w * 0.75)

        out = []
        for y in range(h):
            li = y - top
            if 0 <= li < len(lines):
                src = lines[li]
                # window [offset, offset+w) with wraparound
                vis = (src[offset:] + src)[:w] if bw >= w else \
                      (src * (w // bw + 2))[offset:offset + w]
                buf, last = [], None
                for x, ch in enumerate(vis):
                    if ch == " ":
                        buf.append(" ")
                        continue
                    u = ((x + offset) % period) / period
                    c = theme.cycle((u + ctx.t * 0.1) % 1.0) if theme.hsv \
                        else theme.color_at(u)
                    if c != last:
                        buf.append(rgb(*c))
                        last = c
                    buf.append(ch)
                buf.append(RESET)
                out.append("".join(buf))
            else:
                out.append("")
        return "\n".join(out)
