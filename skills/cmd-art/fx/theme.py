"""Themes: named palettes + gradient helpers, injected into every frame.

A :class:`Theme` is a small, frozen bundle of RGB *stops* plus a background. Effects
never bake in hex values; they sample the active theme (``theme.color_at(t)`` for a
multi-stop gradient, ``theme.cycle(phase)`` for an HSV/lolcat sweep, ``theme.primary``
for an accent). Swapping the theme therefore restyles every effect for free.

Pure stdlib (``colorsys`` only). Colors are ``(r, g, b)`` int triples in 0..255.
"""
from __future__ import annotations

import colorsys
import random
from dataclasses import dataclass, field

RGB = tuple[int, int, int]


# --------------------------------------------------------------------------
# Free functions (usable without a Theme instance)
# --------------------------------------------------------------------------
def clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else 1.0 if t > 1.0 else t


def lerp_color(c0: RGB, c1: RGB, t: float) -> RGB:
    """Per-channel integer interpolation between two RGB colors, ``t`` in 0..1."""
    t = clamp01(t)
    return (
        int(c0[0] + (c1[0] - c0[0]) * t),
        int(c0[1] + (c1[1] - c0[1]) * t),
        int(c0[2] + (c1[2] - c0[2]) * t),
    )


def gradient(stops: tuple[RGB, ...], t: float) -> RGB:
    """Sample a multi-stop gradient. ``t`` in 0..1 maps across all *stops* evenly."""
    n = len(stops)
    if n == 0:
        return (255, 255, 255)
    if n == 1:
        return stops[0]
    t = clamp01(t)
    scaled = t * (n - 1)
    i = int(scaled)
    if i >= n - 1:
        return stops[-1]
    return lerp_color(stops[i], stops[i + 1], scaled - i)


def hsv_color(h: float, s: float = 1.0, v: float = 1.0) -> RGB:
    """HSV (all 0..1, hue wraps) to an RGB int triple."""
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, clamp01(s), clamp01(v))
    return (int(r * 255), int(g * 255), int(b * 255))


def lolcat_color(i: float, freq: float = 0.1, spread: float = 3.0) -> RGB:
    """Classic lolcat rainbow: sine-offset RGB along an index ``i``."""
    import math
    a = i / spread
    r = math.sin(freq * a + 0) * 127 + 128
    g = math.sin(freq * a + 2 * math.pi / 3) * 127 + 128
    b = math.sin(freq * a + 4 * math.pi / 3) * 127 + 128
    return (int(r), int(g), int(b))


# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Theme:
    """A named palette. ``stops`` runs dark/base -> bright/accent.

    Semantic accessors: ``base`` (first stop), ``primary`` (last/brightest stop),
    ``accent`` (a mid-high stop). ``color_at(t)`` samples the whole gradient;
    ``cycle(phase)`` gives an HSV rainbow sweep independent of the stops.
    """

    name: str
    stops: tuple[RGB, ...]
    background: RGB = (0, 0, 0)
    hsv: bool = False  # when True, effects that can should prefer cycle() over stops

    def color_at(self, t: float) -> RGB:
        """Multi-stop gradient sample, ``t`` in 0..1."""
        return gradient(self.stops, t)

    def cycle(self, phase: float, sat: float = 1.0, val: float = 1.0) -> RGB:
        """HSV/lolcat color at ``phase`` (0..1, wraps). Theme-independent rainbow."""
        return hsv_color(phase, sat, val)

    @property
    def base(self) -> RGB:
        return self.stops[0]

    @property
    def primary(self) -> RGB:
        return self.stops[-1]

    @property
    def accent(self) -> RGB:
        return self.stops[min(len(self.stops) - 1, max(0, (len(self.stops) * 2) // 3))]


# --------------------------------------------------------------------------
# Curated palettes
# --------------------------------------------------------------------------
THEMES: dict[str, Theme] = {
    "mono": Theme("mono", ((25, 25, 25), (130, 130, 130), (255, 255, 255))),
    "fire": Theme(
        "fire",
        ((10, 0, 0), (140, 20, 0), (240, 90, 0), (255, 190, 40), (255, 255, 210)),
    ),
    "ocean": Theme(
        "ocean",
        ((3, 10, 40), (10, 60, 130), (20, 140, 200), (90, 210, 230), (220, 250, 255)),
    ),
    "synthwave": Theme(
        "synthwave",
        ((20, 0, 40), (90, 10, 120), (200, 30, 160), (255, 70, 130), (60, 220, 240)),
    ),
    "viridis": Theme(
        "viridis",
        ((68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)),
    ),
    "pastel": Theme(
        "pastel",
        ((90, 80, 110), (170, 200, 240), (200, 230, 200), (250, 210, 230), (255, 245, 220)),
    ),
    "matrix-green": Theme(
        "matrix-green",
        ((0, 20, 0), (0, 90, 20), (0, 180, 50), (120, 255, 140), (220, 255, 220)),
    ),
    "rainbow": Theme(
        "rainbow",
        ((255, 0, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255), (0, 0, 255), (255, 0, 255)),
        hsv=True,
    ),
}

DEFAULT_THEME = "synthwave"


def get_theme(name: str | None) -> Theme:
    """Look up a theme by name (case-insensitive). Falls back to the default theme."""
    if not name:
        return THEMES[DEFAULT_THEME]
    return THEMES.get(name.lower().strip(), THEMES[DEFAULT_THEME])


def theme_names() -> list[str]:
    return list(THEMES.keys())


def random_theme() -> Theme:
    return random.choice(list(THEMES.values()))
