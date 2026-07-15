#!/usr/bin/env python3
"""test_sixel.py — Sixel encoder regression (deterministic, pure-memory).

Locks the wire format against the VT330/340 spec's known-good facts:
  * DCS introducer ESC P 0;1;0 q, ST terminator ESC \\, raster attrs "1;1;W;H,
  * char = 0x3F + mask, bit0 = TOP pixel (verified via the canonical DEC "HI" math),
  * color registers #Pc;2;R;G;B with R/G/B in 0..100 PERCENT (not 0..255),
  * `$` between colors in a band (never trailing), `-` between bands (bands-1 of them),
  * a round-trip: decode the emitted stream back to a pixel grid and compare.

No terminal, no process — the bytes are checked structurally + by decode.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "skills" / "tui-ui"))

from ui.sixel import (encode_sixel, _quantize_index, _index_to_pct,  # noqa: E402
                      raster_to_sixel)

failures = 0


def check(cond, label, detail=""):
    global failures
    if not cond:
        failures += 1
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  -- {detail}" if detail else ""))


RED = (255, 0, 0)
BLUE = (0, 0, 255)
WHITE = (255, 255, 255)


def test_red_blue_fixture():
    """Spec worked example: 2px x 6px, col0 red, col1 blue. One band, two colors."""
    px = [[RED, BLUE] for _ in range(6)]
    s = encode_sixel(px)
    check(s.startswith("\x1bP0;1;0q"), "starts with DCS ESC P 0;1;0 q", repr(s[:9]))
    check(s.endswith("\x1b\\"), "ends with ST ESC backslash")
    check('"1;1;2;6' in s, "raster attrs 1:1 aspect + WxH = 2x6")
    ri, bi = _quantize_index(RED), _quantize_index(BLUE)
    check(_index_to_pct(ri) == (100, 0, 0), "red register defined as 100;0;0 percent",
          str(_index_to_pct(ri)))
    check(_index_to_pct(bi) == (0, 0, 100), "blue register defined as 0;0;100 percent",
          str(_index_to_pct(bi)))
    # red column0 = all 6 rows lit = mask 63 = '~'; its column1 empty = '?'
    check(f"#{ri}~?" in s, "red pass: col0 all-six '~', col1 none '?'",
          f"want #{ri}~?")
    check("$" in s, "a graphics-CR '$' separates the two colors in the band")
    check(f"#{bi}?~" in s, "blue pass: col0 '?', col1 all-six '~'", f"want #{bi}?~")
    check(s.count("-") == 0, "single band -> no graphics-NL '-'", f"count={s.count('-')}")


def test_bit_math_matches_dec_hi_example():
    """The canonical DEC 'HI' example proves char=0x3F+mask, bit0=top:
       '~'=0x7E->63 (all six), '@'=0x40->1 (top only), '}'=0x7D->62 (top off)."""
    check(chr(0x3F + 0b111111) == "~", "mask 63 (all six) encodes to '~'")
    check(chr(0x3F + 0b000001) == "@", "mask 1 (top pixel only) encodes to '@'")
    check(chr(0x3F + 0b111110) == "}", "mask 62 (top off, rest on) encodes to '}'")
    check(chr(0x3F + 0) == "?", "mask 0 (no pixels) encodes to '?'")
    # a single top-lit pixel in a 1x1 image must emit '@' for its color.
    s = encode_sixel([[RED]])
    ri = _quantize_index(RED)
    check(f"#{ri}@" in s, "1x1 top pixel -> sixel char '@' (bit0=top)")


def test_percent_scaling_not_255():
    """Colors must be 0..100 percent, never 0..255 (the classic gotcha)."""
    for c in (RED, BLUE, WHITE, (128, 64, 200)):
        r, g, b = _index_to_pct(_quantize_index(c))
        check(0 <= r <= 100 and 0 <= g <= 100 and 0 <= b <= 100,
              f"{c} -> percent in 0..100", f"got {(r, g, b)}")


def test_band_advance_count():
    """A 2-wide x 13-tall image spans ceil(13/6)=3 bands -> exactly 2 '-'."""
    px = [[WHITE, WHITE] for _ in range(13)]
    s = encode_sixel(px)
    check(s.count("-") == 2, "13 rows -> 3 bands -> 2 graphics-NL", f"count={s.count('-')}")
    check(not s.rstrip("\x1b\\").endswith("-"), "no trailing '-' before ST")


def _decode_sixel(s: str):
    """Minimal decoder for our own output: returns {(x,y): register} for lit px.
    Enough to prove the encoder is self-consistent (round-trip)."""
    body = s
    assert body.startswith("\x1bP")
    body = body[2:]
    # strip params up to the 'q'
    body = body[body.index("q") + 1:]
    body = body[:body.rindex("\x1b\\")]
    lit = {}
    band = 0
    x = 0
    cur = None
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == '"':                       # raster attrs: skip to next control
            j = i + 1
            while j < n and body[j] not in "#$-":
                j += 1
            i = j
            continue
        if ch == '#':                       # color: #Pc or #Pc;2;r;g;b
            j = i + 1
            num = ""
            while j < n and body[j].isdigit():
                num += body[j]; j += 1
            if j < n and body[j] == ';':    # definition — skip the ;2;r;g;b
                while j < n and body[j] not in "#$-?~" and not (0x3F <= ord(body[j]) <= 0x7E and body[j] not in ";0123456789"):
                    j += 1
                # after a definition the register is also selected
            cur = int(num)
            x = 0
            i = j
            continue
        if ch == '$':                       # CR: same band, back to x=0
            x = 0; i += 1; continue
        if ch == '-':                       # NL: next band
            band += 1; x = 0; i += 1; continue
        if ch == '!':                       # RLE: !Pn<char>
            j = i + 1; num = ""
            while j < n and body[j].isdigit():
                num += body[j]; j += 1
            rep = int(num); sc = body[j]
            mask = ord(sc) - 0x3F
            for _ in range(rep):
                for dy in range(6):
                    if mask & (1 << dy):
                        lit[(x, band * 6 + dy)] = cur
                x += 1
            i = j + 1
            continue
        if 0x3F <= ord(ch) <= 0x7E:         # a data char
            mask = ord(ch) - 0x3F
            for dy in range(6):
                if mask & (1 << dy):
                    lit[(x, band * 6 + dy)] = cur
            x += 1
            i += 1
            continue
        i += 1
    return lit


def test_round_trip():
    """Encode a known pattern, decode our own stream, confirm lit pixels match."""
    # 3x6 checkerboard of red/blue
    px = [[RED if (x + y) % 2 == 0 else BLUE for x in range(3)] for y in range(6)]
    s = encode_sixel(px)
    lit = _decode_sixel(s)
    ri, bi = _quantize_index(RED), _quantize_index(BLUE)
    good = True
    for y in range(6):
        for x in range(3):
            want = ri if (x + y) % 2 == 0 else bi
            if lit.get((x, y)) != want:
                good = False
    check(good, "round-trip: decoded pixels match the source checkerboard",
          f"{len(lit)} lit px")


def test_transparent_pixels_skipped():
    """None pixels must not be painted (P2=1 transparent)."""
    px = [[RED, None], [None, RED]]  # 2x2, diagonal
    s = encode_sixel(px)
    lit = _decode_sixel(s)
    ri = _quantize_index(RED)
    check(lit.get((0, 0)) == ri and lit.get((1, 1)) == ri, "lit diagonal present")
    check((1, 0) not in lit and (0, 1) not in lit, "None pixels stay transparent")


def test_raster_adapter():
    """raster_to_sixel forwards a SubcellRaster's .px buffer."""
    from ui.raster import SubcellRaster
    r = SubcellRaster(2, 2, "quad")   # pw=4, ph=4
    r.px[0][0] = RED
    s = raster_to_sixel(r)
    check(s.startswith("\x1bP") and s.endswith("\x1b\\"), "raster adapter emits a DCS")
    check('"1;1;4;4' in s, "raster adapter uses the pixel-buffer dims (4x4)")


def test_empty_image():
    s = encode_sixel([])
    check(s == "\x1bP0;1;0q\x1b\\", "empty image -> bare DCS+ST wrapper", repr(s))


def main():
    for fn in (test_red_blue_fixture, test_bit_math_matches_dec_hi_example,
               test_percent_scaling_not_255, test_band_advance_count,
               test_round_trip, test_transparent_pixels_skipped,
               test_raster_adapter, test_empty_image):
        fn()
    print("-" * 60)
    if failures:
        print(f"test_sixel FAIL -- {failures} check(s) failed")
        return 1
    print("test_sixel PASS -- sixel wire format locked to spec")
    return 0


if __name__ == "__main__":
    sys.exit(main())
