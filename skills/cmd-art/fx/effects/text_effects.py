"""text_effects.py — TTE-style text intros built on the TextEffect base.

Three ways to make a word appear:
  * text_flyin   — each character flies in from off-screen to its place
  * text_converge — characters converge from a scattered cloud to the word
  * text_decrypt — each cell churns through random glyphs, then locks to target

All are pure frame producers; each character's start/scramble is a deterministic
hash of its index so the animation is stable (no per-frame RNG flicker). Motion
is eased via fx.easing. See _texteffect.TextEffect.
"""
from __future__ import annotations

import math

from ..base import Param, FrameCtx
from ..registry import register
from ._texteffect import TextEffect

_GLYPHS = "!@#$%^&*()_+-=[]{}<>?/\\|01"


def _hash01(i, salt=0):
    """Deterministic pseudo-random in [0,1) from an integer + salt."""
    x = (i * 2654435761 + salt * 40503 + 12345) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 1274126177) & 0xFFFFFFFF
    return (x & 0xFFFFFF) / 0x1000000


@register
class TextFlyIn(TextEffect):
    name = "text_flyin"
    aliases = ("flyin",)
    description = "Text intro: each character flies in from off-screen and lands."
    tags = ("text", "intro", "motion")
    DURATION = 2.6
    params = (
        Param("text", "str", "SMARTCLI", "text to animate in"),
        Param("easing", "str", "out_back", "easing curve for the landing"),
    )

    def char_state(self, tc, ctx: FrameCtx, prog: float, total: int):
        tr, tc0, _g, i = tc
        # per-character stagger: later characters start a bit later
        n = max(1, total)
        d = i / n * 0.4                       # up to 40% stagger
        p = self._ease(ctx)(max(0.0, (prog - d) / (1 - d)) if d < 1 else prog)
        # start off-screen in a hashed direction
        ang = _hash01(i, 1) * 2 * math.pi
        dist = 1.0 - p
        sr = tr + math.sin(ang) * ctx.height * dist
        sc = tc0 + math.cos(ang) * ctx.width * dist
        return sr, sc, True


@register
class TextConverge(TextEffect):
    name = "text_converge"
    aliases = ("converge",)
    description = "Text intro: characters converge from a scattered cloud into the word."
    tags = ("text", "intro", "motion")
    DURATION = 2.8
    params = (
        Param("text", "str", "SMARTCLI", "text to animate in"),
        Param("easing", "str", "in_out_cubic", "easing curve"),
    )

    def char_state(self, tc, ctx: FrameCtx, prog: float, total: int):
        tr, tc0, _g, i = tc
        p = self._ease(ctx)(prog)
        # scattered start anywhere on the canvas (hashed), lerp to target
        sr0 = _hash01(i, 7) * ctx.height
        sc0 = _hash01(i, 13) * ctx.width
        return sr0 + (tr - sr0) * p, sc0 + (tc0 - sc0) * p, True


@register
class TextDecrypt(TextEffect):
    name = "text_decrypt"
    aliases = ("decrypt_text",)
    description = "Text intro: each cell churns through random glyphs, then locks."
    tags = ("text", "intro", "reveal")
    DURATION = 2.4
    params = (
        Param("text", "str", "SMARTCLI", "text to reveal"),
    )

    def char_state(self, tc, ctx: FrameCtx, prog: float):
        # decrypt stays in place; the churn is in the glyph, handled below.
        tr, tc0, _g, _i = tc
        return tr, tc0, True

    def render(self, ctx: FrameCtx) -> str:
        # Override to swap the glyph while unlocked (base draws tc[2] directly).
        from ..util import new_grid, grid_to_str
        w, h = ctx.width, ctx.height
        targets = self._targets(ctx.params.get("text", "SMARTCLI"), w, h)
        prog = min(1.0, ctx.t / self.DURATION) if self.DURATION > 0 else 1.0
        grid = new_grid(w, h)
        n = max(1, len(targets))
        for tr, tc0, glyph, i in targets:
            lock_at = 0.2 + _hash01(i, 3) * 0.7      # each cell locks at its own time
            if 0 <= tr < h and 0 <= tc0 < w:
                if prog >= lock_at:
                    ch = glyph
                    col = ctx.theme.color_at(min(1.0, 0.4 + 0.6 * prog))
                else:
                    # churn: pick a glyph that changes over time (deterministic)
                    j = int((ctx.t * 20 + i) % len(_GLYPHS))
                    ch = _GLYPHS[j]
                    col = ctx.theme.color_at(0.2)
                grid[tr][tc0] = (ch, col)
        return grid_to_str(grid)
