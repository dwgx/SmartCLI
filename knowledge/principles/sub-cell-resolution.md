# Sub-Cell Resolution

**Statement:** Unicode block, half-block, quadrant, sextant, and Braille glyphs pack multiple sub-pixels into one cell, multiplying effective resolution beyond the cell grid.

**Real params / glyph ranges (from chafa image->terminal):**
```
Half-block:  ▀ U+2580, ▄ U+2584  -> one cell = 2 vertical pixels (top=fg, bottom=bg for ▀).
Block elements U+2580..U+259F: full ▄█ U+2588, left ▌ U+258C, right ▐ U+2590, shades ░▒▓.
Braille U+2800..U+28FF:  cp = 0x2800 + bitmask, 2x4 dot grid -> 8 sub-cells (8x8 coverage mask).
Sextant U+1FB00..U+1FB3B (Symbols for Legacy Computing): 2x3 subcells, bit = y*2 + x.

Symbol matching per cell (chafa):
  error(symbol,fg,bg) = Σ_pixels color_distance(image[p], symbol_coverage[p] ? fg : bg)
  keep the min-error (symbol, fg, bg) triple.

Fractional bars (cava/progress) — eighth-cell vertical precision:
  full █ U+2588, fractional U+2581..U+2587;  full = bars/8, frag = bars % 8.
  horizontal eighths: █▉▊▋▌▍▎▏ = U+2588..U+258F  (map fractional remainder).
  Rich progress uses HALF-cell precision: full ━, halves ╺ / ╸.
```

**Source:** https://github.com/hpjansson/chafa (chafa-symbols.c / chafa-symbol-renderer.c; eighth-block bar quantization from cava https://github.com/karlstav/cava , both in project research R1 PART B; progress half/eighth precision from R7 §6)

**See also:** [[cell-grid-model]], [[terminal-cell-aspect-ratio]], [[box-drawing-glyphs]], [[cell-width-measurement]]
