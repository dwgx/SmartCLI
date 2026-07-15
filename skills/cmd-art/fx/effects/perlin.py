"""Perlin noise — flowing gradient-noise field (knowledge -> effect).

Implements [[perlin-noise]] (Ken Perlin's 2002 improved noise): fade curve,
hashed corner gradients, trilinear interpolation. Sampled as 3D noise with the
third axis = time, so the field flows like drifting clouds. Rendered as
truecolor background cells colored by the noise value.

Pure frame producer: (t, w, h) -> one frame string. No I/O, no ANSI modes.
"""
from __future__ import annotations

import colorsys

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register

# Perlin's reference permutation (first entries), doubled to 512 to avoid wrap
# math. The full 256-entry table from https://cs.nyu.edu/~perlin/noise/.
_PERM = [151, 160, 137, 91, 90, 15, 131, 13, 201, 95, 96, 53, 194, 233, 7, 225,
    140, 36, 103, 30, 69, 142, 8, 99, 37, 240, 21, 10, 23, 190, 6, 148, 247,
    120, 234, 75, 0, 26, 197, 62, 94, 252, 219, 203, 117, 35, 11, 32, 57, 177,
    33, 88, 237, 149, 56, 87, 174, 20, 125, 136, 171, 168, 68, 175, 74, 165,
    71, 134, 139, 48, 27, 166, 77, 146, 158, 231, 83, 111, 229, 122, 60, 211,
    133, 230, 220, 105, 92, 41, 55, 46, 245, 40, 244, 102, 143, 54, 65, 25, 63,
    161, 1, 216, 80, 73, 209, 76, 132, 187, 208, 89, 18, 169, 200, 196, 135,
    130, 116, 188, 159, 86, 164, 100, 109, 198, 173, 186, 3, 64, 52, 217, 226,
    250, 124, 123, 5, 202, 38, 147, 118, 126, 255, 82, 85, 212, 207, 206, 59,
    227, 47, 16, 58, 17, 182, 189, 28, 42, 223, 183, 170, 213, 119, 248, 152,
    2, 44, 154, 163, 70, 221, 153, 101, 155, 167, 43, 172, 9, 129, 22, 39, 253,
    19, 98, 108, 110, 79, 113, 224, 232, 178, 185, 112, 104, 218, 246, 97, 228,
    251, 34, 242, 193, 238, 210, 144, 12, 191, 179, 162, 241, 81, 51, 145, 235,
    249, 14, 239, 107, 49, 192, 214, 31, 181, 199, 106, 157, 184, 84, 204, 176,
    115, 121, 50, 45, 127, 4, 150, 254, 138, 236, 205, 93, 222, 114, 67, 29, 24,
    72, 243, 141, 128, 195, 78, 66, 215, 61, 156, 180]
_P = _PERM + _PERM   # doubled -> p[512]


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(t, a, b):
    return a + t * (b - a)


def _grad(h, x, y, z):
    h &= 15
    u = x if h < 8 else y
    v = y if h < 4 else (x if h in (12, 14) else z)
    return (u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v)


def _noise(x, y, z):
    X, Y, Z = int(x) & 255, int(y) & 255, int(z) & 255
    x -= int(x); y -= int(y); z -= int(z)
    u, v, w = _fade(x), _fade(y), _fade(z)
    p = _P
    A = p[X] + Y; AA = p[A] + Z; AB = p[A + 1] + Z
    B = p[X + 1] + Y; BA = p[B] + Z; BB = p[B + 1] + Z
    return _lerp(w,
        _lerp(v, _lerp(u, _grad(p[AA], x, y, z), _grad(p[BA], x - 1, y, z)),
                 _lerp(u, _grad(p[AB], x, y - 1, z), _grad(p[BB], x - 1, y - 1, z))),
        _lerp(v, _lerp(u, _grad(p[AA + 1], x, y, z - 1), _grad(p[BA + 1], x - 1, y, z - 1)),
                 _lerp(u, _grad(p[AB + 1], x, y - 1, z - 1), _grad(p[BB + 1], x - 1, y - 1, z - 1))))


_OCTAVES = 4          # fractal Brownian motion: sum of octaves for natural depth
_LACUNARITY = 2.0     # frequency multiplier per octave
_GAIN = 0.5           # amplitude falloff per octave
# Normalizer so fBm output stays in ~[-1,1]: sum of gains 0.5+0.25+...
_FBM_NORM = sum(_GAIN ** o for o in range(_OCTAVES))


def _fbm(x, y, z):
    """Fractal Brownian motion: stack octaves of noise at rising frequency and
    falling amplitude — the standard trick that turns one flat noise layer into
    something with large shapes AND fine detail (clouds, terrain)."""
    total = 0.0
    freq = 1.0
    amp = 1.0
    for _ in range(_OCTAVES):
        total += _noise(x * freq, y * freq, z * freq) * amp
        freq *= _LACUNARITY
        amp *= _GAIN
    return total / _FBM_NORM


def _perlin_frame(t, width, height, palette, theme, scale):
    z = t * 0.3
    lines = []
    for row in range(height):
        out = []
        last = None
        ny = row * scale * 2.0   # ×2: cells are ~2:1, keep the field isotropic
        for col in range(width):
            nx = col * scale
            n = (_fbm(nx, ny, z) + 1.0) * 0.5     # fBm [-1,1] -> [0,1]
            n = 0.0 if n < 0 else (1.0 if n > 1 else n)
            if palette == "rgb":
                rf, gf, bf = colorsys.hsv_to_rgb(n, 0.8, 1.0)
                c = (int(rf * 255), int(gf * 255), int(bf * 255))
            elif palette == "theme" and theme is not None:
                c = theme.cycle(n) if theme.hsv else theme.color_at(n)
            else:
                g = int(n * 255)
                c = (g, g, g)
            if c != last:
                out.append(rgb(*c, bg=True))
                last = c
            out.append(" ")
        lines.append("".join(out) + RESET)
    return "\n".join(lines)


@register
class Perlin(Effect):
    name = "perlin"
    aliases = ("noise", "clouds")
    description = "Flowing Perlin gradient-noise field (drifting clouds)."
    tags = ("field", "noise", "math")
    preferred_theme = "ocean"
    default_fps = 20.0
    params = (
        Param("palette", "str", "theme", "color source", choices=("theme", "hsv", "rgb")),
        Param("scale", "float", 0.08, "noise frequency (smaller = larger blobs)",
              min=0.01, max=0.5),
    )

    def render(self, ctx: FrameCtx) -> str:
        return _perlin_frame(ctx.t, ctx.width, ctx.height,
                             ctx.params["palette"], ctx.theme, ctx.params["scale"])
