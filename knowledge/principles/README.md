# Terminal Rendering Principles

Cross-linked knowledge graph for terminal rendering: how a character-cell grid, ANSI/VT escape sequences, sub-cell glyphs, aspect ratio, flicker-free drawing, and tmux behavior fit together. Each entry is one focused concept with an exact formula/sequence/config and an authoritative source. Links are wiki-style `[[filename-slug]]`.

## Foundations
- [[cell-grid-model]] — the screen is a `W x H` grid of `{ch,fg,bg,attr}` cells; everything resolves to writing cells, not pixels.
- [[ansi-sgr-color]] — SGR escapes set color/attrs; exact 24-bit and 256-color sequences + palette math.
- [[cursor-and-screen-control]] — cursor/clear/alt-screen/mouse VT sequences and the canonical exit teardown.
- [[flicker-free-rendering]] — build a full frame, write once over a home-positioned screen; double/z-buffer discipline.

## Geometry & measurement
- [[terminal-cell-aspect-ratio]] — cells are ~2:1 tall:wide; correct circles/3D or they render squashed.
- [[sub-cell-resolution]] — half-block, quadrant, sextant, Braille and eighth-bars pack sub-pixels into one cell.
- [[cell-width-measurement]] — use `wcwidth`/UAX #11 cell width, never `len()`; wide=2, control/zero-width handling.

## Layout on the grid
- [[box-model-on-cell-grid]] — CSS-like margin/border/padding/content where borders are whole cells; box-sizing math.
- [[fractional-space-distribution]] — carry-remainder / cumulative-floor `fr` resolution so track totals never drift.
- [[box-drawing-glyphs]] — real Unicode U+2500..U+257F border table; why to avoid DEC ACS line-drawing.

## tmux behavior
- [[truecolor-passthrough-tmux]] — tmux forwards RGB only if the outer terminal is advertised RGB; else it quantizes.
- [[tmux-alternate-screen]] — per-pane alt-screen buffer; smcup/rmcup restore discipline and hard-kill leaks.
- [[resize-sigwinch-handling]] — SIGWINCH is a dimensionless dirty flag; re-query size + full redraw (Windows polls).
- [[tmux-capture-pane]] — scrape a pane with `capture-pane`; join wraps + strip SGR for text, keep `-e` for color.
- [[tmux-launch-and-sizing]] — popup (fixed overlay, not scrapeable) vs split (layout, scrapeable); resize-pane syntax.
