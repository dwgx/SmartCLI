"""_noiselib.py — noise-composition primitives shared by the field effects.

Builds on perlin.py's improved-noise kernel (reused verbatim, no second impl)
and adds the techniques that lift plain fBm to "natural material" quality:
  * fbm(x,y,z)          — the base fractal Brownian motion (from perlin.py)
  * ridged(x,y,z)       — 1 - |2·fbm - 1|, the bright-filament / caustic ridge
  * domain_warp(x,y,t)  — Inigo Quilez's fbm(p + fbm(p + fbm(p))): warp the
                          noise by itself so smooth turbulence becomes flowing
                          filaments (fire, clouds, nebula). Returns (f, qx, qy)
                          so callers can drive multi-color mixing off q.
  * black_body(k)       — Tanner Helland's temperature(Kelvin)->RGB, the physical
                          fire/incandescence ramp (black->red->orange->white).

The leading underscore keeps the effect registry (which scans effects/*.py) from
treating this as an Effect module.

Sources:
  domain warping   https://iquilezles.org/articles/warp/
  black-body ramp  https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html
"""
from __future__ import annotations

import math

from .effects.perlin import _noise  # reuse the improved-noise kernel


def fbm(x, y, z, octaves=4, lacunarity=2.0, gain=0.5):
    """Fractal Brownian motion — sum of noise octaves. Output ~[-1, 1]."""
    total = 0.0
    freq = 1.0
    amp = 1.0
    norm = 0.0
    for _ in range(octaves):
        total += _noise(x * freq, y * freq, z * freq) * amp
        norm += amp
        freq *= lacunarity
        amp *= gain
    return total / norm if norm else 0.0


def ridged(x, y, z, octaves=4):
    """Ridged noise: 1 - |2·fbm - 1| in [0,1]. Sharp bright ridges — the basis
    of water caustic nets and nebula filaments."""
    n = (fbm(x, y, z, octaves) + 1.0) * 0.5   # -> [0,1]
    return 1.0 - abs(2.0 * n - 1.0)


def domain_warp(x, y, t, warp=4.0):
    """IQ domain warping: f(p) = fbm(p + warp·q), q = fbm(p + offsets).

    Returns (f, qx, qy) in roughly [-1,1] each. q is the first warp field —
    callers use its magnitude/components to mix extra colors (nebula), or just
    take f for a flowing scalar field (fire/clouds). t animates the field.
    """
    qx = fbm(x, y, t)
    qy = fbm(x + 5.2, y + 1.3, t)
    rx = fbm(x + warp * qx + 1.7, y + warp * qy + 9.2, t)
    ry = fbm(x + warp * qx + 8.3, y + warp * qy + 2.8, t)
    f = fbm(x + warp * rx, y + warp * ry, t)
    return f, qx, qy


# --- black-body / fire color ramp -----------------------------------------
def black_body(kelvin):
    """Temperature (K) -> (r,g,b), 0..255. Tanner Helland's fit, ~1000-40000K.
    Black at low K, deep red, orange, yellow-white toward ~6500K+."""
    t = max(1000.0, min(40000.0, kelvin)) / 100.0
    # red
    if t <= 66:
        r = 255.0
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
    # green
    if t <= 66:
        g = 99.4708025861 * math.log(t) - 161.1195681661
    else:
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
    # blue
    if t >= 66:
        b = 255.0
    elif t <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(t - 10) - 305.0447927307
    return (int(max(0, min(255, r))),
            int(max(0, min(255, g))),
            int(max(0, min(255, b))))
