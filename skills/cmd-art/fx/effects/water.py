"""Water — sum-of-sines swell + noise ripples + caustic net (knowledge -> effect).

A moving water surface: several sine waves (different directions/frequencies)
sum into a height field, small fBm ripples perturb it, and two offset ridged-
noise layers multiply into a caustic net of bright interlacing lines. Depth is
colored deep-blue -> cyan by height; caustics add cyan-white highlights.
See _noiselib.

Pure frame producer: (t, w, h) -> one frame string. No I/O, no ANSI modes.
"""
from __future__ import annotations

import math

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register
from .._noiselib import fbm, ridged

_DEEP = (6, 22, 70)      # trough / deep water
_SHAL = (30, 120, 190)   # crest / shallow
_FOAM = (180, 240, 255)  # caustic highlight

# sine wave directions (unit-ish) + frequencies + speeds
_WAVES = [
    (1.0, 0.0, 0.20, 1.0),
    (0.4, 0.9, 0.31, 0.7),
    (-0.7, 0.5, 0.17, 1.3),
    (0.2, -1.0, 0.25, 0.9),
]


def _mix(c0, c1, u):
    u = 0.0 if u < 0 else (1.0 if u > 1 else u)
    return (int(c0[0] + (c1[0] - c0[0]) * u),
            int(c0[1] + (c1[1] - c0[1]) * u),
            int(c0[2] + (c1[2] - c0[2]) * u))


def _water_frame(t, width, height, speed, use_theme, theme):
    lines = []
    for row in range(height):
        y = row * 2.0            # ×2 cell aspect
        out = []
        last = None
        for col in range(width):
            x = float(col)
            # sum-of-sines height field; exp(sin-1) sharpens crests (Gerstner-ish)
            h = 0.0
            for (dx, dy, freq, spd) in _WAVES:
                phase = (dx * x + dy * y) * freq + t * spd * speed
                h += math.exp(math.sin(phase) - 1.0)
            h /= len(_WAVES)                              # ~[0,1]
            h += 0.12 * fbm(x * 0.15, y * 0.15, t * 0.2)  # fine ripples
            h = 0.0 if h < 0 else (1.0 if h > 1 else h)
            if use_theme and theme is not None:
                c = theme.color_at(h)
            else:
                c = _mix(_DEEP, _SHAL, h)
            # caustic net: two offset ridged layers multiplied -> bright grid
            caus = (ridged(x * 0.18, y * 0.18, t * 0.3)
                    * ridged(x * 0.18 + 4.0, y * 0.18 + 4.0, t * 0.25))
            if caus > 0.72:
                c = _mix(c, _FOAM, (caus - 0.72) / 0.28 * 0.8)
            if c != last:
                out.append(rgb(*c, bg=True))
                last = c
            out.append(" ")
        lines.append("".join(out) + RESET)
    return "\n".join(lines)


@register
class Water(Effect):
    name = "water"
    aliases = ("ocean", "waves")
    description = "Water surface: sum-of-sines swell + ripples + caustic highlights."
    tags = ("field", "water", "noise")
    preferred_theme = "ocean"
    default_fps = 24.0
    params = (
        Param("speed", "float", 1.0, "wave speed", min=0.1, max=4.0),
        Param("palette", "str", "ocean", "color source", choices=("ocean", "theme")),
    )

    def render(self, ctx: FrameCtx) -> str:
        return _water_frame(ctx.t, ctx.width, ctx.height, ctx.params["speed"],
                            ctx.params["palette"] == "theme", ctx.theme)
