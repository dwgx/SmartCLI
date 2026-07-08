# notcurses — sub-cell blitter geometry

A C rendering library whose value here is its catalog of sub-cell "pixel" blitters and the hard rule that governs them: only two colors per cell.

**Source:** https://github.com/dankamongmen/notcurses

## How it works
- **Blitters** subdivide a character cell into a sub-pixel grid, each mapped to a Unicode glyph:
  - `2x1` half-blocks (aspect-preserving),
  - `2x2` quadrants,
  - `3x2` sextants (×1.5 vertical stretch),
  - `4x2` octants,
  - `BRAILLE` (4×2 dots),
  - `PIXEL` (true sixel / kitty graphics).
- **Hard constraint:** a cell can carry only **2 colors** (one fg, one bg). So each cell picks one glyph + two colors; if more than two sub-regions differ, you must interpolate down to two.
- The default blitter is chosen by target scale and glyph availability.
- Planes: z-ordered `ncplane`s are flattened by the **painter's algorithm** in `ncpile_render_internal` (walks `p->top` down `pl->below`, so higher planes claim each cell first; the 2-color rule is enforced by alpha-gated `cell_blend_fchannel`/`cell_blend_bchannel`). `ncpile_rasterize` then turns the flat framebuffer into an escape stream (postpaint high-contrast lock + damage-detect, emitting only `damaged` cells). **Truecolor terminals get raw RGB (no quantization); only 256/8-color paths quantize** (`rgb_quantize_256`/`rgb_quantize_8`). *(verified in src/lib/render.c, 2026-07-08)*

## What to borrow
- The **blitter geometry table** (2x1 / 2x2 / 3x2 / 4x2 / braille / pixel) as the menu of options for image and graph rendering across terminal capabilities.
- The **"2 colors per cell"** rule as the fundamental design constraint for all sub-cell art — it's *why* half-block and braille rendering must reduce color before choosing a glyph.

## See also
- [[sub-cell-resolution]]
- [[image-to-ansi-halfblock]]
- [[nearest-color-downgrade]]
