"""sixel.py — Sixel graphics protocol output (pure stdlib).

raster.py resolves pixels DOWN to sub-cell glyphs (half/quad/sextant/braille) so
images show on any terminal. Sixel is the escape hatch UP: terminals that support
it (Windows Terminal >=1.22, xterm, mlterm, WezTerm, mintty) render true bitmap
graphics from an in-band DCS escape string. This module encodes an RGB pixel grid
(e.g. a SubcellRaster's ``.px`` buffer) into that string.

The wire format (VT330/340 sixel spec + Dankwardt "All About SIXELs"):

  * DCS introducer   ``ESC P P1;P2;P3 q``   — we emit ``ESC P 0;1;0 q``:
      P1=0 (aspect deprecated; use raster attrs instead), P2=1 (zero-bits are
      TRANSPARENT — required so overprinting several colors in one band doesn't
      erase earlier colors), P3=0.
  * raster attrs     ``"Pan;Pad;Ph;Pv``     — we emit ``"1;1;W;H`` (1:1 square px).
  * color register   ``#Pc;2;R;G;B``        — Pu=2 (RGB), R/G/B in 0..100 PERCENT.
  * select color     ``#Pc``
  * one data byte    encodes a COLUMN of 6 vertical pixels for the current color:
      ``chr(0x3F + mask)`` where bit0 = TOP pixel (weight 1) .. bit5 = bottom (32).
      Range ``?``(0x3F, none) .. ``~``(0x7E, all six).
  * ``$``  graphics CR  — back to left margin of the SAME band (overprint next color).
  * ``-``  graphics NL  — down to the next band (== down exactly 6 pixel rows).
  * ``!Pn<char>``       — run-length: repeat the following sixel char Pn times.
  * ST terminator    ``ESC \\``.

Encoding is band-based: process 6 pixel-rows at a time; for each color present in
the band emit its column bitmasks (RLE-compressed), separated by ``$``; advance to
the next band with ``-``.

Colors are quantized to a fixed 6x6x6 cube (216 colors, well under the 256-register
ceiling) — trivial, no image passes, decent for UI/graphics.
"""
from __future__ import annotations

import sys
from typing import List, Optional, Sequence, Tuple

RGB = Tuple[int, int, int]

# DCS / ST controls (always 7-bit forms — 8-bit C1 breaks on UTF-8 paths).
_DCS = "\x1bP"
_ST = "\x1b\\"

# 6x6x6 color cube: 6 evenly-spaced levels per channel -> 216 palette entries.
_LEVELS = (0, 51, 102, 153, 204, 255)          # i*255/5
_LEVEL_PCT = tuple(round(v * 100 / 255) for v in _LEVELS)  # (0,20,40,60,80,100)


def _quantize_index(c: RGB) -> int:
    """RGB (0..255) -> palette register 0..215 in the 6x6x6 cube."""
    r, g, b = c
    ri = 0 if r < 0 else 5 if r > 255 else (r + 25) // 51   # round to nearest of 6
    gi = 0 if g < 0 else 5 if g > 255 else (g + 25) // 51
    bi = 0 if b < 0 else 5 if b > 255 else (b + 25) // 51
    return 36 * ri + 6 * gi + bi


def _index_to_pct(idx: int) -> Tuple[int, int, int]:
    """Palette register -> (R%, G%, B%) for the color-definition command."""
    ri, rem = divmod(idx, 36)
    gi, bi = divmod(rem, 6)
    return (_LEVEL_PCT[ri], _LEVEL_PCT[gi], _LEVEL_PCT[bi])


def _flush_run(parts: List[str], ch: str, n: int) -> None:
    """Emit ``ch`` repeated ``n`` times, RLE-compressed when it pays off (n>=4)."""
    if n <= 0:
        return
    if n >= 4:
        parts.append(f"!{n}{ch}")
    else:
        parts.append(ch * n)


def encode_sixel(pixels: Sequence[Sequence[Optional[RGB]]]) -> str:
    """Encode a 2D grid of ``Optional[RGB]`` pixels (rows of columns) to a Sixel
    DCS string. ``None`` pixels are transparent (P2=1: left unpainted).

    ``pixels[y][x]`` is the pixel at row y, column x. Rows may be ragged only in
    that trailing rows can be shorter; width is taken as the max row length.
    Returns the complete ``ESC P ... ESC \\`` string, ready to write to a
    sixel-capable terminal. An empty image returns just the empty DCS+ST wrapper.
    """
    height = len(pixels)
    width = max((len(row) for row in pixels), default=0)
    if width == 0 or height == 0:
        return _DCS + "0;1;0q" + _ST

    # Collect the palette registers actually used, in first-seen order (dict keys
    # preserve insertion order; the value carries no meaning — the register's RGB
    # is recomputed from its index at emission via _index_to_pct).
    used: dict[int, None] = {}
    for row in pixels:
        for c in row:
            if c is not None:
                used.setdefault(_quantize_index(c), None)

    parts: List[str] = [_DCS, "0;1;0q", f'"1;1;{width};{height}']
    for idx in used:
        r, g, b = _index_to_pct(idx)
        parts.append(f"#{idx};2;{r};{g};{b}")

    num_bands = (height + 5) // 6
    for band in range(num_bands):
        y0 = band * 6
        # Which palette registers appear anywhere in this 6-row band.
        band_colors: List[int] = []
        seen = set()
        for dy in range(6):
            y = y0 + dy
            if y >= height:
                break
            for c in pixels[y]:
                if c is not None:
                    idx = _quantize_index(c)
                    if idx not in seen:
                        seen.add(idx)
                        band_colors.append(idx)

        first_color = True
        for idx in band_colors:
            if not first_color:
                parts.append("$")          # CR: overprint on the same band
            first_color = False
            parts.append(f"#{idx}")
            # Build one sixel char per column for this color, RLE-compressed.
            run_char: Optional[str] = None
            run_len = 0
            for x in range(width):
                mask = 0
                for dy in range(6):
                    y = y0 + dy
                    if y < height and x < len(pixels[y]):
                        c = pixels[y][x]
                        if c is not None and _quantize_index(c) == idx:
                            mask |= 1 << dy      # bit0 = top pixel
                ch = chr(0x3F + mask)
                if ch == run_char:
                    run_len += 1
                else:
                    _flush_run(parts, run_char, run_len)  # type: ignore[arg-type]
                    run_char = ch
                    run_len = 1
            _flush_run(parts, run_char, run_len)  # type: ignore[arg-type]

        if band < num_bands - 1:
            parts.append("-")             # NL: advance to the next 6-row band

    parts.append(_ST)
    return "".join(parts)


def raster_to_sixel(raster) -> str:
    """Encode a :class:`ui.raster.SubcellRaster`'s pixel buffer to a Sixel string.

    The raster's ``.px`` is already a ``ph x pw`` grid of ``Optional[RGB]`` — the
    exact shape :func:`encode_sixel` wants — so this just forwards it. Note the
    raster's pixel buffer is square (the ASPECT=2 correction is in the cell
    subdivision), so ``"1;1`` (1:1) is the correct aspect.
    """
    return encode_sixel(raster.px)


def supports_sixel(timeout: float = 0.3) -> Optional[bool]:
    """Best-effort DA1 probe: does the current terminal report Sixel support?

    Writes the Primary Device Attributes query ``ESC[c`` and reads the reply,
    which looks like ``ESC [ ? 62 ; 4 ; ... c``. Sixel support is advertised by
    the attribute ``4`` appearing in that list. Returns:
      * ``True``  — the reply contained ``4`` (sixel-capable),
      * ``False`` — a reply arrived without ``4``,
      * ``None``  — could not determine (no TTY, no reply within *timeout*, or a
        platform where we can't do the raw round-trip). Never raises.

    On POSIX this uses raw-tty + select. On Windows a reliable raw console read
    needs VT-input mode that we don't set up here, so it returns ``None`` (unknown)
    rather than guessing — prefer treating Windows Terminal >=1.22 as capable by
    other means if you need a definite answer there.
    """
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return None
    except Exception:
        return None

    if sys.platform == "win32":
        return None  # no reliable raw-console DA1 round-trip here; unknown.

    try:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            sys.stdout.write("\x1b[c")
            sys.stdout.flush()
            buf = ""
            # read until the final 'c' of the DA1 reply, or timeout
            while True:
                r, _, _ = select.select([fd], [], [], timeout)
                if not r:
                    break
                ch = sys.stdin.read(1)
                if not ch:
                    break
                buf += ch
                if ch == "c":
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return None

    # Parse the params between 'ESC [ ?' and 'c'; sixel = attribute 4.
    if "\x1b[" not in buf or "c" not in buf:
        return None
    body = buf.split("\x1b[", 1)[1].rstrip("c").lstrip("?")
    params = body.replace(":", ";").split(";")
    return "4" in params


def print_sixel(pixels_or_raster, file=None) -> None:
    """Encode and write a Sixel image in one flush.

    Accepts either a raw ``pixels[y][x]`` grid or an object with a ``.px``
    attribute (a SubcellRaster). Emits the whole DCS as a single write so nothing
    interleaves inside the escape (which would corrupt it).
    """
    f = file if file is not None else sys.stdout
    px = getattr(pixels_or_raster, "px", pixels_or_raster)
    f.write(encode_sixel(px))
    try:
        f.flush()
    except Exception:
        pass
