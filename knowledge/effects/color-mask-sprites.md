# Color-Mask Sprites (glyph layer + parallel color layer)

Colorize static ASCII art by keeping two aligned layers of identical dimensions: a **glyph layer** (the characters) and a **color-mask layer** (one color code per cell). One art asset can be recolored without editing the glyphs — the reusable trick from `asciiquarium`, and the same content-vs-color separation Copilot CLI's banner uses.

## The two-layer model
```
glyph:  "  ><((('>"          color: "  rrbbwwy "     # same shape, per-cell color key
```
- Each color-mask cell names a color for the glyph at that position (space/blank = inherit or transparent).
- Render walks both layers together: emit an SGR color from the mask, then the glyph from the art.
- `copilot-cli-banner` generalizes the mask to a `"row,col" → semantic-role` map (4-bit roles like `eyes`/`border`), then **run-length groups** consecutive same-color cells into segments to cut escape writes.

## Depth for scenes (painter's algorithm)
Multi-sprite scenes carry an integer **depth** per entity and draw far→near — cheaper and simpler than a pixel z-buffer when entities are whole sprites (contrast the z-buffered surface in [[donut-c]]).

## Borrow
- Split the **content string** from the color map so art and palette evolve independently (theme-aware degradation, recoloring).
- Run-length segment batching minimizes escape writes.
- Integer-depth painter's order for compositing sprites.

**Source:** https://github.com/cmatsuoka/asciiquarium (parallel color-mask) and the Copilot CLI banner engineering post (semantic-role map); distilled in `../sources/deep-art.md` §11

## See also
- [[asciiquarium]]
- [[copilot-cli-banner]]
- [[sprite-scroll]]
- [[ansi-sgr-color]]
- [[cell-grid-model]]
