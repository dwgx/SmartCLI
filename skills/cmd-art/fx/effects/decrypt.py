"""Movie-style decrypt reveal: glyph noise resolves into the real text.

Per char: ``start = i*stagger + jitter``, ``lock = start + scramble``. Before
start -> blank; before lock -> random cipher glyph (refreshed every few
frames, colored theme base/accent); after -> final char in theme.primary.
Source: research/R1 part D.1 (GSAP ScrambleText / TTE Decrypt).
"""
from __future__ import annotations

import random

from ..core import RESET, rgb
from ..base import Effect, FrameCtx, Param
from ..registry import register

GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&*+-/<>?[]{}"


@register
class Decrypt(Effect):
    name = "decrypt"
    description = "Scramble-to-plaintext reveal (per-char start/lock schedule)."
    tags = ("text", "reveal", "matrix")
    preferred_theme = "matrix-green"
    default_fps = 20.0
    params = (
        Param("text", "str", "ACCESS GRANTED: SMARTCLI ONLINE",
              "text to reveal (use \\n for line breaks)"),
        Param("stagger", "float", 0.06, "seconds between char starts", min=0.0, max=1.0),
        Param("scramble", "float", 0.9, "avg scramble duration seconds", min=0.05, max=5.0),
        Param("seed", "int", 7, "RNG seed for the schedule"),
    )

    def setup(self) -> None:
        self._sched = None
        self._scratch = {}

    def _schedule(self, text, p):
        if self._sched is None:
            rng = random.Random(p["seed"])
            sched = []
            for i, ch in enumerate(text):
                start = 0.2 + i * p["stagger"] + rng.uniform(0, p["stagger"] * 2)
                lock = start + rng.uniform(p["scramble"] * 0.5, p["scramble"] * 1.5)
                sched.append((start, lock))
            self._sched = sched
        return self._sched

    def render(self, ctx: FrameCtx) -> str:
        p = ctx.params
        text = p["text"].replace("\\n", "\n")
        sched = self._schedule(text, p)
        theme = ctx.theme
        ink = rgb(*theme.primary)
        dim = rgb(*theme.color_at(0.45))
        refresh = ctx.frame_index // 3  # mutate cipher glyphs every 3 frames

        # center the block
        lines = text.split("\n")
        top = max(0, (ctx.height - len(lines)) // 2)
        rows = [""] * ctx.height
        idx = 0
        for li, line in enumerate(lines):
            y = top + li
            left = max(0, (ctx.width - len(line)) // 2)
            buf = [" " * left]
            for ch in line:
                start, lock = sched[idx]
                if ch == " " or ctx.t >= lock:
                    buf.append(ink + ch)
                elif ctx.t >= start:
                    key = (idx, refresh)
                    g = self._scratch.get(key)
                    if g is None:
                        if len(self._scratch) > 4096:  # drop stale refresh keys
                            self._scratch.clear()
                        g = random.choice(GLYPHS)
                        self._scratch[key] = g
                    buf.append(dim + g)
                else:
                    buf.append(" ")
                idx += 1
            idx += 1  # the newline itself
            if 0 <= y < ctx.height:
                rows[y] = "".join(buf) + RESET
        return "\n".join(rows)

    def teardown(self) -> None:
        self._sched = None
        self._scratch = {}
