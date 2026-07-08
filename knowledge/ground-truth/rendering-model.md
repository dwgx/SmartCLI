# Rendering Model — The tui-ui Theoretical Kernel (pointer)

**Statement:** Every terminal widget is a composition of four low-level primitives over one axiom: **the terminal is a discrete `cols × rows` grid of `Cell = (glyph, fg, bg, attrs)`** — no pixels, no continuous coordinates. Any new effect must answer "which primitives compose it?" If it can't, the primitive set needs extending, not another bespoke widget.

This is a **pointer** into a load-bearing skill document (the full theory lives with the tui-ui skill). The four kernel primitives:

1. **CellField — everything is a shader field.** Any renderable is a pure function `S(x, y, t) → Sample(glyph, fg, bg, alpha)`. Ripple, glow, gradient, plasma, fire, scanlines are all just different `S`. The engine samples every cell, alpha-composites, run-length serializes. Composition is field algebra: `over(A,B)`, `add`, `mask`, spatial transforms.
   - **Geometric truth (most important):** char cells are ~2× tall as wide, so `ASPECT = 2.0`. Any isotropic/circular metric must correct y: `dist = sqrt((x-ox)^2 + ((y-oy)*ASPECT)^2)`. The `/effort` ripple's `((row-2)*2)^2` is exactly this. Ignore it → circles become vertical bars. See [[terminal-cell-aspect-ratio]].
   - Built-in field vocabulary (each ~10 lines): `Ripple`, `RadialGlow`, `LinearGradient`, `Plasma`, `Noise/Fire`.
2. **SubcellRaster — sub-cell resolution (the source of smoothness).** Whole cells are blocky; encode sub-pixels with special glyphs: half-block `▀▄` + dual fg/bg = 1×2 px/cell, quadrants = 2×2, Braille U+2800..U+28FF = 2×4. Render into a real pixel buffer → downsample to glyph+color. See [[sub-cell-resolution]].
3. **BoxJunction — structure is connection algebra.** Don't hand-place `─│┌┐`. Each cell records 4 edge weights `edge[N,E,S,W] ∈ {0,1,2,3}`; glyph = pure lookup `LOOKUP[(n,e,s,w)]`. Crossings, thin-meets-thick, rounded panels all grow from one table. See [[box-drawing-glyphs]] / [[box-drawing]].
4. **ColorModel — honest color and alignment.** Truecolor SGR; **honest degrade** truecolor→256→16→mono (must actually downgrade, not pretend); **width alignment** via `wcwidth` (CJK/emoji = 2 cells); serialize SGR only on style change (run-length), reset at line end, CRLF line breaks. See [[ansi-sgr-color]], [[cell-width-measurement]], [[nearest-color-downgrade]].

**Litmus test (does the kernel hold?):** gradient divider = one `LinearGradient` row; ultracode glow = `Ripple` washing a panel with white text over; smooth progress bar = `SubcellRaster`; panel/table/tree = `BoxJunction` + content field; **`/effort` selector = layout + one `Ripple` field + text over** — a kernel composition plus ~12 lines of field, not a bespoke script.

**Source:** Load-bearing project document (unsourced / primary): `D:/Project/SmartCLI/skills/tui-ui/references/RENDERING-MODEL.md`.

**See also:** [[cell-grid-model]], [[terminal-cell-aspect-ratio]], [[sub-cell-resolution]], [[box-drawing-glyphs]], [[ansi-sgr-color]], [[flicker-free-rendering]], [[effort-selector]], [[hard-lessons]], [[plasma]], [[color-interpolation]]
