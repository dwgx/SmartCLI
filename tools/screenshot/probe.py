"""probe.py -- inspect raw fx FRAME STRINGS (before pyte) for geometry defects.

The matrix checks run on pyte's rendered grid, which pyte clamps to `cols` --
so an effect that emits over-wide rows or the wrong row count is masked. Here we
measure the raw frame string each effect returns, per size, at several t values
(text/progressive effects vary with t). This catches:
  * over-wide rows   (visible width > ctx.width)  -> wrap/truncation damage
  * wrong row count  (rows != ctx.height)         -> under/overfill
  * blank frame      (no visible glyph AND no SGR) -> renders empty
"""
from __future__ import annotations

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CMD_ART = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "skills", "cmd-art")
for p in (_HERE, _CMD_ART):
    if p not in sys.path:
        sys.path.insert(0, p)

import fx.registry as registry
from fx.base import FrameCtx
from fx.theme import get_theme

_SGR = re.compile(r"\x1b\[[0-9;:]*m")
_ANSI = re.compile(r"\x1b\[[0-9;:?]*[A-Za-z]")


def visible_width(line: str) -> int:
    """Width in cells after stripping SGR/ANSI, counting wide glyphs as 2."""
    from wcwidth import wcswidth  # if unavailable, fall back below
    s = _ANSI.sub("", line)
    w = wcswidth(s)
    return w if w >= 0 else len(s)


def visible_width_fallback(line: str) -> int:
    import unicodedata
    s = _ANSI.sub("", line)
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        elif unicodedata.combining(ch):
            w += 0
        else:
            w += 1
    return w


try:
    import wcwidth  # noqa
    _vw = visible_width
except Exception:
    _vw = visible_width_fallback

SIZES = [(40, 12), (80, 24), (120, 40), (200, 50)]
TVALS = [0.0, 0.35, 0.7, 1.5, 3.0, 6.0]


def main():
    registry.load_all()
    problems = []
    for cls in registry.all_effects():
        name = cls.name
        for (cols, rows) in SIZES:
            for t in TVALS:
                eff = cls()
                eff.setup()
                try:
                    ctx = FrameCtx(t=t, frame_index=int(t * 30), width=cols,
                                   height=max(1, rows - 1),
                                   theme=get_theme(cls.preferred_theme),
                                   params=cls.param_defaults())
                    frame = eff.render(ctx)
                finally:
                    try:
                        eff.teardown()
                    except Exception:
                        pass
                lines = frame.split("\n")
                exp_rows = max(1, rows - 1)
                # geometry
                overwide = [(i, _vw(ln)) for i, ln in enumerate(lines)
                            if _vw(ln) > cols]
                # visible content: any non-space glyph OR any SGR color
                stripped = _ANSI.sub("", frame)
                has_glyph = bool(stripped.strip())
                has_sgr = bool(_SGR.search(frame))
                blank = not has_glyph and not has_sgr
                if overwide:
                    mx = max(w for _, w in overwide)
                    problems.append(f"OVERWIDE {name} {cols}x{rows} t={t}: "
                                    f"{len(overwide)} rows, max width {mx} > {cols}")
                if len(lines) != exp_rows:
                    problems.append(f"ROWCOUNT {name} {cols}x{rows} t={t}: "
                                    f"{len(lines)} rows != {exp_rows}")
                if blank:
                    problems.append(f"BLANK {name} {cols}x{rows} t={t}: "
                                    f"no visible glyph and no SGR")
    if not problems:
        print("PROBE: no geometry/blank defects across all effects/sizes/t-values")
    else:
        print(f"PROBE: {len(problems)} potential defects")
        for p in problems:
            print("  " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
