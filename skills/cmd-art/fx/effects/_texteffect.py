"""_texteffect.py — base class for character-motion text effects (TTE-style).

TerminalTextEffects animates a string by giving each character a start state, a
target position, and an eased path between them. We do the same in our pure-
frame-producer model: __init__ rasterizes the text (via text3d.big_text — figlet
or the built-in block font) into a list of target characters, and render(ctx)
places each character at its eased position for the current time, drawing the
whole grid. Subclasses only decide each character's START position and reveal
timing; the base handles rasterization, centering, easing, and compositing.

Leading underscore: this is a base module, not a registered Effect.

Reference: TerminalTextEffects motion model (Character/Waypoint/Path + easing).
https://github.com/ChrisBuilds/terminaltexteffects
"""
from __future__ import annotations

from ..base import Effect, FrameCtx
from ..core import RESET, rgb
from ..util import new_grid, grid_to_str
from .text3d import big_text
from .. import easing


class TextEffect(Effect):
    """Base for text effects: rasterize -> per-character eased motion -> frame.

    Subclasses implement ``char_state(self, tc, ctx, prog)`` returning the
    character's current (row, col, visible) given its target ``tc`` = (tr, tc0,
    glyph, idx) and a global progress ``prog`` in [0,1]. The base computes
    ``prog`` from ctx.t and DURATION, centers the text block, and composites.
    """
    DURATION = 3.0        # seconds for the intro animation to complete
    default_fps = 30.0

    def _targets(self, text, w, h):
        """Rasterize text and center it -> list of (row, col, glyph, index)."""
        lines = big_text(text)
        bh = len(lines)
        bw = max((len(ln) for ln in lines), default=0)
        top = max(0, (h - bh) // 2)
        left = max(0, (w - bw) // 2)
        out = []
        idx = 0
        for r, ln in enumerate(lines):
            for c, ch in enumerate(ln):
                if ch != " " and top + r < h and left + c < w:
                    out.append((top + r, left + c, ch, idx))
                    idx += 1
        return out

    # subclass hook -------------------------------------------------------
    def char_state(self, tc, ctx: FrameCtx, prog: float, total: int):
        """Return (row, col, visible) for target char ``tc`` = (tr, tc0, glyph,
        idx). ``total`` is the character count (for staggering). Default: static."""
        tr, tc0, _glyph, _i = tc
        return tr, tc0, True

    def color_for(self, tc, ctx: FrameCtx, prog: float):
        """Color of a character. Default: theme gradient across its progress."""
        return ctx.theme.color_at(min(1.0, 0.3 + 0.7 * prog))

    def render(self, ctx: FrameCtx) -> str:
        w, h = ctx.width, ctx.height
        targets = self._targets(ctx.params.get("text", "SMARTCLI"), w, h)
        total = len(targets)
        prog = min(1.0, ctx.t / self.DURATION) if self.DURATION > 0 else 1.0
        grid = new_grid(w, h)
        for tc in targets:
            row, col, visible = self.char_state(tc, ctx, prog, total)
            if not visible:
                continue
            ri, ci = int(round(row)), int(round(col))
            if 0 <= ri < h and 0 <= ci < w:
                grid[ri][ci] = (tc[2], self.color_for(tc, ctx, prog))
        return grid_to_str(grid)

    def _ease(self, ctx, default="out_cubic"):
        return easing.get(ctx.params.get("easing", default))
