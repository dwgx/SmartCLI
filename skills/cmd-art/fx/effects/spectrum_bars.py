"""Spectrum bars: a synthesized signal driven through cava's meter pipeline.

Vertical meter bars with log-spaced bins, gravity-fall + integral smoothing, and
eighth-block [[sub-cell-resolution]] rendering -- the reusable half of cava's
``cavacore.c``. There is no real audio here (an Effect is a pure frame
producer), so the "signal" is a deterministic sum of moving sines placed at
log-spaced pseudo-frequencies; what is faithful to cava is the SMOOTHING and the
RENDER: eighth-blocks ``U+2581..U+2587`` layered over the full block ``U+2588``
via ``frac*8``, and the gravity (accelerating fall) + integral (memory) decay
filter that gives the bars their springy settle.

Source: https://github.com/karlstav/cava (verified cavacore.c) via
knowledge/effects/spectrum-bars.md.
"""
from __future__ import annotations

import math

from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..util import grid_to_str, new_grid

# Full block + the seven partial eighth-blocks (index = round(frac*8)).
# _EIGHTHS[0] is a space (empty); [8] is the full block.
_EIGHTHS = " ▁▂▃▄▅▆▇█"


class Spectrum:
    """Per-bar smoothed meter state, updated toward a target each frame.

    ``vals`` holds the current *displayed* normalized height (0..1) per bar.
    ``mem`` is the integral-smoothing memory, ``peak`` / ``fall`` drive the
    accelerating gravity fall (from cava's cavacore.c smooth-decay).
    """

    def __init__(self, bars: int, framerate: float, noise_reduction: float):
        self.bars = bars
        self.noise_reduction = noise_reduction
        fr_mod = 66.0 / max(1.0, framerate)
        # accelerating gravity fall + integral memory coefficients.
        self.gravity_mod = pow(fr_mod, 2.5) * 2.0 / max(0.1, noise_reduction)
        self.integral_mod = pow(fr_mod, 0.1)
        self.vals = [0.0] * bars
        self.mem = [0.0] * bars
        self.peak = [0.0] * bars
        self.fall = [0.0] * bars
        self._primed = False

    def _target(self, n: int, t: float) -> float:
        """Synthesized bar magnitude in 0..1 at (bar n, time t).

        Log-spaced pseudo-frequency per bar; a few detuned moving sines make the
        bars dance the way an audio spectrum does. Bass bars (low n) sit higher,
        matching a typical pink-ish spectrum tilt.
        """
        # log-spaced position 0..1 across the bar range (perceptually even).
        p = math.log10(1.0 + 9.0 * n / max(1, self.bars - 1))
        freq = 0.7 + 6.5 * p
        a = (
            0.55 * math.sin(freq * t * 1.7 + n * 0.35)
            + 0.30 * math.sin(freq * t * 0.9 + n * 0.11 + 1.3)
            + 0.15 * math.sin(freq * t * 2.6 + n * 0.57 + 2.1)
        )
        env = 1.0 - 0.55 * p          # bass-tilt: lows louder than highs
        v = env * (0.5 + 0.5 * a)     # map sine sum into 0..1
        return v if v > 0.0 else 0.0

    def update(self, t: float) -> None:
        targets = [self._target(n, t) for n in range(self.bars)]
        if not self._primed:
            # first frame: sit on the target so a single-frame render (contract
            # test / gallery) shows a full spectrum, not an empty grid.
            self.vals = list(targets)
            self.mem = list(targets)
            self.peak = list(targets)
            self._primed = True
            return
        for n in range(self.bars):
            tgt = targets[n]
            out = tgt
            # gravity fall: when the bar dips below its peak, let it accelerate down.
            if out < self.vals[n]:
                self.fall[n] += 0.028
                fallen = self.peak[n] * (1.0 - self.fall[n] * self.fall[n]
                                         * self.gravity_mod)
                out = max(out, fallen if fallen > 0.0 else 0.0)
            else:
                self.peak[n] = out
                self.fall[n] = 0.0
            # integral (memory) smoothing.
            out = self.mem[n] * self.noise_reduction / self.integral_mod + out
            if out > 1.0:
                out = 1.0
            self.mem[n] = out
            self.vals[n] = out


@register
class SpectrumBars(Effect):
    name = "spectrum_bars"
    description = "Audio-style spectrum meter: log bins, gravity smoothing, eighth-blocks."
    aliases = ("spectrum", "bars")
    tags = ("audio", "meter", "generative")
    preferred_theme = "viridis"
    default_fps = 30.0
    params = (
        Param("gap", "int", 1, "empty columns between bars (0 = solid)", min=0, max=4),
        Param("noise_reduction", "float", 0.77, "smoothing 0..1 (higher = smoother)",
              min=0.05, max=0.99),
        Param("mono", "bool", False, "plain ASCII (no color)"),
    )

    def setup(self) -> None:
        self._spec = None
        self._size = None

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        gap = ctx.params["gap"]
        step = gap + 1
        # number of bars that fit, one glyph column each with `gap` spacing.
        bars = (w + gap) // step
        if bars < 1:
            bars = 1

        if self._spec is None or self._size != (w, h):
            self._size = (w, h)
            self._spec = Spectrum(bars, self.default_fps,
                                  ctx.params["noise_reduction"])
        self._spec.update(ctx.t)

        mono = ctx.params["mono"]
        theme = ctx.theme
        grid = new_grid(w, h)
        # eighths of a cell available over the full height.
        max_eighths = h * 8
        for n in range(bars):
            x = n * step
            if x >= w:
                break
            filled = int(round(self._spec.vals[n] * max_eighths))
            if filled <= 0:
                continue
            full_rows = filled // 8
            partial = filled % 8
            # draw full blocks from the bottom up.
            for r in range(full_rows):
                y = h - 1 - r
                if y < 0:
                    break
                tone = (r + 1) / h            # bottom dim -> top bright
                color = None if mono else theme.color_at(tone if tone < 1 else 1.0)
                grid[y][x] = (_EIGHTHS[8], color)
            # one partial block on top of the stack.
            if partial and full_rows < h:
                y = h - 1 - full_rows
                if 0 <= y < h:
                    tone = (full_rows + 1) / h
                    color = None if mono else theme.color_at(tone if tone < 1 else 1.0)
                    grid[y][x] = (_EIGHTHS[partial], color)
        return grid_to_str(grid)

    def teardown(self) -> None:
        self._spec = None
        self._size = None
