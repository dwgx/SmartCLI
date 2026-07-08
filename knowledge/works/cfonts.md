# cfonts — tagged block-font glyph grids

A JS/CLI figlet-alternative that renders text in block fonts defined as fixed-height glyph grids, with inline color tags for two-tone glyphs.

**Source:** https://github.com/dominikwilkowski/cfonts (verified: `fonts/block.json`)

## How it works
- A font is JSON: a header (`name`, `version`, `colors`, `lines`, `buffer`, `letterspace`, `letterspace_size`) plus `chars[c]` = an array of exactly `lines` row-strings for that character.
- Multi-color glyphs embed `<c1>…</c1><c2>…</c2>` tags inside the row-strings; at render, the tags are swapped for ANSI color (body vs. shadow, for example).
- Gradient modes: normal 2-color, `-t` transition across n stops, `-i` per-line independent gradient.

## What to borrow
- The `<cN>`-tagged, fixed-`lines` glyph-grid format for two-tone block fonts (body vs. shadow) — cleaner than lolcat-style post-hoc coloring because color intent is authored *into* the glyph.
- Fixed-height `lines` grids make layout trivial (no smushing math, unlike FIGfont — contrast [[figlet-flf-spec]]).

## See also
- [[figlet-flf-spec]]
- [[box-drawing]]
- [[color-interpolation]]
