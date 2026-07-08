# figlet / FIGfont v2 — the ASCII banner-font spec

FIGlet is the original ASCII banner-text generator; FIGfont v2 is the font-file format it reads. The spec is the reference for large text glyph layout and smushing.

**Source:** http://jave.de/figlet/figfont.html

## How it works
- **Header line:** `flf2a$ H B ML OL CL PD FL CT` — signature + hardblank char (`$` here), then Height, Baseline, Max-Length, Old-Layout, Comment-Lines, Print-Direction, Full-Layout, Codetag-Count.
- **Hardblank** (`$`): a space that survives smushing, so glyph internal spaces aren't collapsed away.
- **Endmark** (`@`): marks the end of each glyph line (`@@` ends the character).
- **Smushing:** 6 horizontal + 5 vertical smushing rules, each with a bit value, letting adjacent glyphs overlap by shared strokes.
- **Layout bitmask:** values `64 / 128 / 8192 / 16384` (and others) in the layout fields select which smush rules apply.

## What to borrow
- The FIGfont format + smushing rules as the reference for rendering large banner text — especially the hardblank concept for preserving intended internal spacing.
- Contrast with [[cfonts]]: FIGfont uses variable-width glyphs + smushing; cfonts uses fixed-height tagged grids. Pick per use.

## See also
- [[figlet-flf-spec]]
- [[cfonts]]
- [[box-drawing]]
