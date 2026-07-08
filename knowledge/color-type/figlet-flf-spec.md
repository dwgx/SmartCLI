# FIGlet .flf / FIGfont Spec

Format for FIGlet ASCII-art fonts: a header line followed by comment lines and per-character sub-glyphs.

Header example: `flf2a$ 6 5 20 15 3 0 143 229`
- `flf2a` signature + hardblank char (`$` here)
- height, baseline, max_length, old_layout, comment_lines
- optional: print_direction, full_layout, codetag_count

Rendering:
- Hardblank (`$`) renders as a space but blocks fitting/smushing (prevents characters from merging there).
- Layout progression: full-width → kerning → smushing.

Horizontal smushing rules (bitvalues):
- 1 equal-char, 2 underscore, 4 hierarchy, 8 opposite-pair,
- 16 big-X (`/\` → `|`, `\/` → `Y`, `><` → `X`), 32 hardblank.
- Vertical smushing rules use bitvalues 256..4096.

**Source:** http://www.figlet.org/figfont.txt

**See also:** [[wcwidth-east-asian-width]], [[box-drawing]]
