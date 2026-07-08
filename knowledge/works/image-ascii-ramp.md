# Image→ASCII brightness ramp (openreplay) — the real pixels→chars

A tutorial that documents the actual image-to-ASCII pipeline: per-pixel luminance mapped into a brightness ramp, optionally with truecolor.

**Source:** https://blog.openreplay.com/ascii-art-browser-terminal/

## How it works
- **Luminance:** `Y = 0.2126*R + 0.7152*G + 0.0722*B` (Rec. 709 weights).
- **Ramp:** `' .:-=+*#%@'` (sparse→dense). Index `idx = floor(Y/255 * (len-1))` picks the glyph.
- **Color (optional):** wrap the glyph in truecolor `\033[38;2;R;G;Bm` using the pixel's own RGB.
- **Aspect:** compensate for the ~2:1 character cell (a cell is about twice as tall as wide) by sampling roughly 2 source rows per output row.

## What to borrow
- The canonical brightness-ramp mapping for turning any image or grayscale field into glyphs — the standard form of [[ascii-luminance-ramp]].
- Pairing the ramp glyph with the source pixel's truecolor is the cheapest step up from monochrome ASCII toward [[image-to-ansi-halfblock]].

## See also
- [[ascii-luminance-ramp]]
- [[image-to-ansi-halfblock]]
- [[terminal-cell-aspect-ratio]]
