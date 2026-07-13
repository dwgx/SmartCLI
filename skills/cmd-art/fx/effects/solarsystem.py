"""3D solar-system orrery: planets on tilted orbits, perspective-projected.

Real 3D: each planet moves on a circular orbit in a plane tilted by ``TILT``
about the x-axis, so orbits render as ellipses seen in perspective (near side
larger, far side smaller and dimmer). Bodies are depth-sorted (painter's
algorithm) and can pass in front of / behind the sun. A camera focal projection
gives true perspective; ASPECT=2 corrects the character-cell shape.

SEAMLESS LOOP: every body completes an INTEGER number of orbits within the loop
window ``LOOP_SECONDS`` (angular speed = turns · 2π / LOOP), and the sun pulse
does an integer number of cycles too — so the state at t=LOOP equals t=0 exactly.
Capture ``LOOP_SECONDS`` worth of frames and the GIF loops with no seam.

Pure frame producer: (t, w, h) -> one frame string. No I/O, no ANSI modes.
"""
from __future__ import annotations

import math

from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..util import grid_to_str, new_grid

ASPECT = 2.0            # a cell is ~2x taller than wide
TILT = 0.62            # orbital-plane tilt (~35°): rings spread, fill top+bottom
FOCAL = 2.4            # camera focal length (perspective strength)
CAM_Z = 3.4           # camera distance from the system centre
LOOP_SECONDS = 12.0    # one seamless loop; capture this many seconds

# (glyph, orbit_radius, turns_per_loop, phase, colour_t)
# turns_per_loop is an INTEGER -> body returns to start at t=LOOP (seamless).
# inner planets take more turns (faster), matching real order.
PLANETS = [
    ("o", 0.42, 6, 0.0, 0.80),   # Mercury
    ("O", 0.62, 5, 1.1, 0.88),   # Venus
    ("O", 0.85, 4, 2.3, 0.55),   # Earth
    ("o", 1.10, 3, 3.7, 0.96),   # Mars (reddish)
    ("@", 1.45, 2, 5.0, 0.34),   # Jupiter (big)
    ("0", 1.80, 1, 0.7, 0.24),   # Saturn
]

SUN_PULSE_CYCLES = 4   # integer -> loops cleanly
SUN_RAMP = "*oO@"
ORBIT_STEPS = 260      # samples per orbit ring (dense -> continuous curve)
TRAIL = 7              # comet-trail segments behind each planet
N_STARS = 90           # fixed backdrop stars (deterministic -> seamless)


def _project(x, y, z, cx, cy, scale):
    """Perspective-project a 3D point to screen (col, row, depth)."""
    zc = CAM_Z - z                      # distance from camera along view axis
    if zc < 0.1:
        zc = 0.1
    f = FOCAL / zc
    sx = cx + x * f * scale
    sy = cy - y * f * scale / ASPECT    # y up; compress for cell aspect
    return sx, sy, zc


@register
class SolarSystem(Effect):
    name = "solarsystem"
    description = "3D orrery: tilted planetary orbits in perspective round a sun."
    tags = ("3d", "space", "simulation")
    aliases = ("orrery", "planets")
    preferred_theme = "synthwave"
    default_fps = 30.0
    params = (
        Param("speed", "float", 1.0, "orbital speed multiplier", min=0.0, max=8.0),
        Param("orbits", "bool", True, "draw tilted orbit rings"),
    )

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        grid = new_grid(w, h)
        depth = [[1e9] * w for _ in range(h)]   # z-buffer (smaller zc = nearer)
        theme = ctx.theme
        cx, cy = w / 2.0, h / 2.0
        sinT, cosT = math.sin(TILT), math.cos(TILT)
        # Calibrate scale so the outermost orbit fills the frame. We measure the
        # projected half-extent of r=1.8 (sampled around the tilted ring) at
        # scale=1, then scale up to fill ~92% of the width and height budgets.
        rmax = 1.8
        hx = hy = 1e-6
        for i in range(48):
            a = i / 48 * math.tau
            oy = rmax * math.sin(a) * cosT
            oz = rmax * math.sin(a) * sinT
            ox = rmax * math.cos(a)
            zc = CAM_Z - oz
            if zc < 0.1:
                zc = 0.1
            f = FOCAL / zc
            hx = max(hx, abs(ox * f))
            hy = max(hy, abs(oy * f) / ASPECT)
        scale = min((w * 0.48) / hx, (h * 0.48) / hy)
        spd = ctx.params["speed"]

        def plot(sx, sy, zc, ch, col, force=False):
            xi, yi = int(round(sx)), int(round(sy))
            if 0 <= xi < w and 0 <= yi < h and (force or zc < depth[yi][xi]):
                depth[yi][xi] = zc
                grid[yi][xi] = (ch, col)

        def orbit_point(r, a):
            ox, oy0 = r * math.cos(a), r * math.sin(a)
            oy = oy0 * cosT
            oz = oy0 * sinT
            return _project(ox, oy, oz, cx, cy, scale)

        base = math.tau / LOOP_SECONDS

        # 0) star backdrop (deterministic pseudo-random -> identical every loop,
        #    so the field never flickers and the loop stays seamless)
        star_col = theme.color_at(0.10)
        s = 12345
        for _ in range(N_STARS):
            s = (s * 1103515245 + 12345) & 0x7fffffff
            sx = s % w
            s = (s * 1103515245 + 12345) & 0x7fffffff
            sy = s % h
            if grid[sy][sx] is None:
                grid[sy][sx] = ("." if (sx + sy) % 5 else "·", star_col)

        # 1) tilted orbit rings — dense sampling makes a continuous curve, and
        #    brightness rises on the near side (bigger f) for a 3-D read.
        if ctx.params["orbits"]:
            for (_g, r, _tn, _ph, _ct) in PLANETS:
                for i in range(ORBIT_STEPS):
                    a = (i / ORBIT_STEPS) * math.tau
                    sx, sy, zc = orbit_point(r, a)
                    near = zc < CAM_Z            # front half of the ring
                    col = theme.color_at(0.34 if near else 0.20)
                    ch = "•" if near else "·"
                    plot(sx, sy, zc + 0.04, ch, col)

        # 2) the sun — a radiant multi-ring core, pulsing (integer cycles)
        pulse = 0.5 + 0.5 * math.sin(ctx.t * base * SUN_PULSE_CYCLES)
        ssx, ssy, sz = _project(0, 0, 0, cx, cy, scale)
        for rad, glyphs, ct in ((0, "@", 0.99), (1, "%", 0.92), (2, "*", 0.82), (3, ".", 0.55)):
            col = theme.color_at(ct)
            steps = max(6, int(rad * 8) + 6)
            for k in range(steps):
                aa = k / steps * math.tau
                gx = ssx + math.cos(aa) * rad
                gy = ssy + math.sin(aa) * rad / ASPECT
                ch = glyphs if rad == 0 else ("*" if (pulse > 0.5 or rad < 3) else ".")
                plot(gx, gy, sz - 0.01, ch, col, force=(rad == 0))

        # 3) planets — integer turns per loop => seamless; each with a comet trail
        bodies = []
        for (glyph, r, turns, phase, ct) in PLANETS:
            ang = phase + ctx.t * base * turns * spd
            px, py0 = r * math.cos(ang), r * math.sin(ang)
            sx, sy, zc = _project(px, py0 * cosT, py0 * sinT, cx, cy, scale)
            bodies.append((zc, sx, sy, glyph, ct, r, ang, turns))

        # paint far -> near so nearer bodies overwrite
        for (zc, sx, sy, glyph, ct, r, ang, turns) in sorted(bodies, key=lambda b: -b[0]):
            # comet trail: previous positions along the orbit, fading
            for tseg in range(TRAIL, 0, -1):
                ta = ang - tseg * 0.06 * turns
                tx, ty0 = r * math.cos(ta), r * math.sin(ta)
                tsx, tsy, tzc = _project(tx, ty0 * cosT, ty0 * sinT, cx, cy, scale)
                fade = 0.20 + 0.5 * (1 - tseg / TRAIL)
                plot(tsx, tsy, tzc + 0.02, "·", theme.color_at(ct * fade))
            # the planet body: a bright core with a small glow halo so it reads
            # as a round body, not a single dim char
            body = theme.color_at(ct)
            halo = theme.color_at(min(0.99, ct + 0.12))
            plot(sx - 1, sy, zc, "(", halo)
            plot(sx, sy, zc, glyph, body)
            plot(sx + 1, sy, zc, glyph, body)
            plot(sx + 2, sy, zc, ")", halo)

        return grid_to_str(grid)
