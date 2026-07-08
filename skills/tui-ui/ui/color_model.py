"""color_model.py — primitive #4: honest color degrade + wcwidth alignment.

Truecolor is the native tier; a terminal declaring 256/16/mono must get a REAL
nearest-color mapping, not a fake. And every renderer must agree on how many
cells a character occupies (CJK/emoji = 2) or columns desync. See
references/RENDERING-MODEL.md §4.
"""
from __future__ import annotations

import unicodedata
from typing import Tuple

RGB = Tuple[int, int, int]

# ── truecolor -> 256 (6x6x6 cube 16..231 + 24 grays 232..255) ──────────────
def _cube6(v: int) -> int:
    # map 0..255 to one of the 6 cube steps (0,95,135,175,215,255)
    if v < 48:
        return 0
    if v < 115:
        return 1
    return min(5, (v - 35) // 40)


def to_256(rgb: RGB) -> int:
    r, g, b = rgb
    # gray ramp candidate
    if abs(r - g) < 8 and abs(g - b) < 8:
        gray = round((r + g + b) / 3)
        if gray < 8:
            return 16
        if gray > 248:
            return 231
        return 232 + min(23, (gray - 8) // 10)
    ri, gi, bi = _cube6(r), _cube6(g), _cube6(b)
    return 16 + 36 * ri + 6 * gi + bi


# ── truecolor -> 16 (standard ANSI palette nearest) ────────────────────────
_ANSI16 = [
    (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
    (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
    (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
]


def to_16(rgb: RGB) -> int:
    r, g, b = rgb
    best, bi = 1e18, 0
    for i, (cr, cg, cb) in enumerate(_ANSI16):
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < best:
            best, bi = d, i
    return bi


# ── truecolor -> mono glyph (luminance ramp for no-color terminals) ────────
_RAMP = " .:-=+*#%@"


def luminance(rgb: RGB) -> float:
    r, g, b = rgb
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def to_mono_char(rgb: RGB, ramp: str = _RAMP) -> str:
    i = int(round(luminance(rgb) * (len(ramp) - 1)))
    return ramp[max(0, min(len(ramp) - 1, i))]


def downgrade(rgb: RGB, depth: str):
    """Dispatch: 'truecolor'->rgb, '256'->int, '16'->int, 'mono'->glyph char."""
    if depth == "truecolor":
        return rgb
    if depth == "256":
        return to_256(rgb)
    if depth == "16":
        return to_16(rgb)
    if depth == "mono":
        return to_mono_char(rgb)
    raise ValueError(f"unknown depth {depth!r}")


# ── wcwidth: how many cells a character occupies ───────────────────────────
def wcwidth(ch: str) -> int:
    if not ch:
        return 0
    cp = ord(ch[0])
    if cp == 0:
        return 0
    # combining / zero-width
    if unicodedata.combining(ch):
        return 0
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf") and cp != 0x00AD:
        return 0
    # East Asian Wide / Fullwidth
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    # common emoji ranges (many are Neutral in EAW tables but render wide)
    if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or (0x1F000 <= cp <= 0x1F0FF):
        return 2
    return 1


def str_width(s: str) -> int:
    return sum(wcwidth(c) for c in s)


if __name__ == "__main__":
    assert 190 <= to_256((255, 0, 0)) <= 200, to_256((255, 0, 0))
    assert to_mono_char((10, 10, 10)) != to_mono_char((250, 250, 250))
    assert str_width("中A") == 3, str_width("中A")
    assert wcwidth("A") == 1 and wcwidth("中") == 2
    print("color_model self-test OK")
