"""Procedural ASCII bonsai: a stochastic turtle grows a tree into a cell grid.

A recursive ``branch(y, x, type, life)`` walk writes glyphs into a mutable grid,
its direction chosen by per-type dice rolls, side-shoots gated by a cooldown --
the [[procedural-branching]] skeleton distilled from cbonsai's ``cbonsai.c``
(lifeStart 32, multiplier 5, five branch types, cooldown-gated shoots). Because
an Effect is a PURE frame producer (no per-character nanosleep like the real
live mode), the whole tree is generated ONCE with a seeded RNG as an ordered
list of draw events, and each frame reveals the prefix that has "grown" by then
-- so the animation is the same tree filling in over time, fully deterministic.

Source: https://gitlab.com/jallbrit/cbonsai (verified cbonsai.c) via
knowledge/effects/procedural-branching.md + knowledge/works/cbonsai.md.
"""
from __future__ import annotations

import random

from ..base import Effect, FrameCtx, Param
from ..registry import register
from ..util import grid_to_str, new_grid

# Branch types (cbonsai's enum, distilled to the five the notes name).
_TRUNK, _SHOOT_L, _SHOOT_R, _DYING, _DEAD = range(5)

_LIFE_START = 32
_MULTIPLIER = 5
_LEAVES = "&*^.,"  # ASCII-safe leaf glyph set (rule 8: no encoding surprises)


class _Grower:
    """Generates one deterministic tree as an ordered list of draw events.

    Each event is ``(y, x, glyph, tone)`` where ``tone`` in 0..1 selects the
    theme color (low = woody branch, high = bright leaf). Draw order IS grow
    order, so revealing a prefix animates the growth.
    """

    def __init__(self, w: int, h: int, seed: int):
        self.w = w
        self.h = h
        self.rng = random.Random(seed)
        self.events: list[tuple[int, int, str, float]] = []
        self._branches = 0
        self._max_branches = max(8, (w * h) // 40)

    # -- direction dice (setDeltas, 5 types) --------------------------------
    def _deltas(self, kind: int, age: int, life: int) -> tuple[int, int]:
        r = self.rng
        if kind == _TRUNK:
            # young leans widely, then straightens; climbs upward on a cadence.
            dx = r.randint(-2, 2) if age <= 2 else r.randint(-1, 1)
            dy = 0 if (age <= 1 or r.random() < 0.2) else -1
        elif kind == _SHOOT_L:
            dx = r.randint(-2, 0)
            dy = r.choice((-1, 0, 0))
        elif kind == _SHOOT_R:
            dx = r.randint(0, 2)
            dy = r.choice((-1, 0, 0))
        elif kind == _DYING:
            dx = r.randint(-3, 3)
            dy = r.choice((-1, 0, 1))
        else:  # _DEAD -- small jitter, leaf cluster
            dx = r.randint(-1, 1)
            dy = r.randint(-1, 1)
        return dx, dy

    # -- direction -> glyph -------------------------------------------------
    def _glyph(self, kind: int, dx: int, dy: int) -> str:
        if kind in (_DYING, _DEAD):
            return self.rng.choice(_LEAVES)
        if dx < 0:
            return "\\" if dy < 0 else "~"
        if dx > 0:
            return "/" if dy < 0 else "~"
        return "|"

    def _tone(self, kind: int) -> float:
        if kind in (_DYING, _DEAD):
            return 0.9              # bright leaves
        if kind in (_SHOOT_L, _SHOOT_R):
            return 0.45             # mid green shoots
        return 0.2                  # woody trunk

    # -- the recursion ------------------------------------------------------
    def _branch(self, y: int, x: int, kind: int, life: int) -> None:
        self._branches += 1
        cooldown = _MULTIPLIER
        while life > 0:
            life -= 1
            age = _LIFE_START - life
            dx, dy = self._deltas(kind, age, life)
            # ground clamp: don't dig below the floor row.
            if dy > 0 and y >= self.h - 2:
                dy = 0
            y += dy
            x += dx
            # keep the turtle on the grid (clamp, never crash on tiny sizes).
            if y < 0:
                y = 0
            elif y > self.h - 1:
                y = self.h - 1
            if x < 0:
                x = 0
            elif x > self.w - 1:
                x = self.w - 1
            self.events.append((y, x, self._glyph(kind, dx, dy), self._tone(kind)))

            if self._branches >= self._max_branches:
                continue
            # cooldown-gated side shoots off the trunk.
            cooldown -= 1
            if kind == _TRUNK and cooldown <= 0 and life > 4:
                side = _SHOOT_L if self.rng.random() < 0.5 else _SHOOT_R
                self._branch(y, x, side, max(4, life // 2))
                cooldown = _MULTIPLIER * 2
            # occasional trunk fork.
            if kind == _TRUNK and life > 7 and self.rng.randint(0, 7) == 0:
                self._branch(y, x, _TRUNK, life - 2)
            # a live shoot tip sprouts a small dead/leaf cluster near its end.
            if kind in (_SHOOT_L, _SHOOT_R) and life <= 2:
                self._branch(y, x, _DEAD, self.rng.randint(2, 4))

    def grow(self) -> list[tuple[int, int, str, float]]:
        # trunk starts at the ground, mid-width, climbing up.
        self._branch(self.h - 1, self.w // 2, _TRUNK, _LIFE_START)
        return self.events


@register
class Cbonsai(Effect):
    name = "cbonsai"
    description = "Procedural ASCII bonsai grown by a stochastic branching turtle."
    tags = ("nature", "procedural", "generative")
    preferred_theme = "matrix-green"
    default_fps = 24.0
    params = (
        Param("seed", "int", 7, "RNG seed (same seed -> same tree)"),
        Param("speed", "float", 55.0, "glyphs revealed per second (grow rate)",
              min=1.0, max=500.0),
        Param("mono", "bool", False, "plain ASCII, no color"),
    )

    def setup(self) -> None:
        self._events = None
        self._size = None
        self._seed = None

    def _ensure(self, w: int, h: int, seed: int) -> None:
        if self._size == (w, h) and self._seed == seed and self._events is not None:
            return
        self._size = (w, h)
        self._seed = seed
        self._events = _Grower(w, h, seed).grow()

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        seed = ctx.params["seed"]
        self._ensure(w, h, seed)
        events = self._events
        speed = ctx.params["speed"]
        mono = ctx.params["mono"]
        theme = ctx.theme

        # how many glyphs have "grown" by now; holds full once complete.
        reveal = int(ctx.t * speed)
        if reveal > len(events):
            reveal = len(events)

        grid = new_grid(w, h)
        for i in range(reveal):
            y, x, glyph, tone = events[i]
            color = None if mono else theme.color_at(tone)
            grid[y][x] = (glyph, color)
        return grid_to_str(grid)

    def teardown(self) -> None:
        self._events = None
        self._size = None
        self._seed = None
