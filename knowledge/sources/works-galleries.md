# Terminal Art: Works, Galleries & Demoscene Sources

Raw findings from surveying galleries/collections/demoscene sources for terminal-art
ideas and techniques we can reproduce in a **cell grid** (pyte screen buffer,
foreground/background per cell, one glyph per cell).

Compiled 2026-07-08. Every entry carries a real URL; techniques were extracted by
WebFetch of primary sources where fetchable.

---

## 1. Subcell resolution techniques (the core trick pool)

The single biggest lever: pack multiple "pixels" into one terminal cell by choosing a
glyph whose lit region matches the sub-cell pattern, plus 2 colors (fg + bg). This is
how every "image in a terminal" tool multiplies apparent resolution.

### Braille (2x4 = 8 subpixels per cell) — drawille
- URL: https://github.com/asciimoo/drawille  (ports: node https://github.com/madbence/node-drawille ,
  go https://github.com/exrook/drawille-go , lua https://github.com/asciimoo/lua-drawille )
- Base codepoint **U+2800** (blank braille). Each of 8 dots = one bit in the low byte.
- Dot bit layout (historical 6-dot + later 2 rows):
  ```
  dot1 0x01   dot4 0x08
  dot2 0x02   dot5 0x10
  dot3 0x04   dot6 0x20
  dot7 0x40   dot8 0x80   <- note: bottom row bits non-contiguous
  ```
- Pixel (x,y) -> cell (x//2, y//4); within-cell bit = pixel_map[y%4][x%2] where
  `pixel_map = ((0x01,0x08),(0x02,0x10),(0x04,0x20),(0x40,0x80))`.
- set_pixel = OR the bit; glyph = `chr(0x2800 + accumulated_bits)`. Sparse dict of cells.
- Gives ~2x horizontal, 4x vertical res. Monochrome per cell (one color) unless extended.

### Quadrants (2x2) / Sextants (2x3) / Octants (2x4) / Half-blocks (1x2) — notcurses blitters
- HN discussion: https://news.ycombinator.com/item?id=24956014  (429'd on fetch — reachable in browser)
- notcurses-info man (lists the glyph families): https://www.mankier.com/1/notcurses-info
- Quadblitter uses Unicode 3.2 **quadrant blocks** to map 2x2 pixels -> 1 cell.
  Unicode 13 added **sextants** (2x3). notcurses also does **octant** and **braille** blitters.
- Key constraint vs braille: block glyphs let you use **2 colors per cell** (fg fills the
  "on" subcells, bg fills the "off" subcells) but only 2x2/2x3 spatial res; braille gives
  2x4 spatial res but effectively **1 color** per cell. Tradeoff = spatial resolution vs
  color fidelity. Pick blitter per-image.

### Half-block (1x2, the workhorse for photos) — U+2580
- StackOverflow reference: https://stackoverflow.com/questions/59864651/how-to-use-the-utf-8-half-block-to-have-two-colors-in-one-character-block
- Print `▀` (U+2580 upper half block) with fg = top pixel color, bg = bottom pixel color.
  One cell = 2 vertically-stacked truecolor pixels. Cell aspect ~1:1 after this. This is
  the simplest, most robust "image to terminal" method; works on any 24-bit terminal.
- Moebius ANSI editor's "half-block brush" is the artist-facing version of this — edit
  "closer to Photoshop than a text editor". https://github.com/blocktronics/moebius

### gnuplot terminal doc — concise summary of all four
- https://gnuplot.sourceforge.net/docs/loc19800.html : "quadrants ... double resolution
  in both directions. sextants uses 2x3 block characters, and braille ... 2x4
  pseudo-resolution." Good cheatsheet.

**Reproduce in our cell grid:** implement a blitter layer that, given a source RGB
bitmap, chooses among half-block / quadrant / sextant / braille and emits (glyph, fg, bg)
per cell. Half-block first (easiest + best color), braille for line-art/plots.

---

## 2. chafa — the reference image-to-ANSI engine
- Home/gallery: https://hpjansson.org/chafa/  and  https://hpjansson.org/chafa/gallery/
- Man page (technique knobs): https://man.archlinux.org/man/chafa.1.en
- Symbol classes selectable via `--symbols`: `all, none, space, solid, stipple, block,
  border, diagonal, dot, quad, half, hhalf, vhalf, inverted, braille, technical,
  geometric, ascii, legacy, sextant, wedge, wide, narrow`. Combine with `+`/`-`,
  ordering significant. Default set: `block+border+space-wide-inverted`.
- Add explicit codepoints (`u2580`), ranges (`u2580..u259f`), literals (`[abcd]`).
- Dithering `--dither none|ordered|diffusion|noise` ("Bayer"=ordered, "fs"=Floyd-Steinberg
  =diffusion). `--dither-grain WxH` in {1,2,4,8}px (a cell = 8px by definition).
  `--dither-intensity` 0..inf, 1.0 neutral.
- Color space `--color-space rgb|din99d` (DIN99d = perceptual, slower, better picks).
- `--color-extractor average|median` (median = crisper, average = better on noise).
- `--work 1-9` accuracy/CPU tradeoff. SIMD + multithreaded. Also emits Sixel/Kitty/iTerm2.
- Core idea (per gallery): "combines Unicode symbols from multiple selectable ranges for
  optimal output" — i.e. brute-force best-glyph match per cell over the enabled symbol set,
  in a perceptual color space, with optional dithering to smooth gradients.

**Reproduce:** per-cell, score every candidate glyph's coverage bitmap against the cell's
source pixels in DIN99d space; keep best (glyph, fg, bg). Ordered/Bayer dither is cheap and
grid-friendly for gradients.

---

## 3. MapSCII — braille vector rendering pipeline (great worked example)
- Repo: https://github.com/rastapasta/mapscii  (live: `telnet mapscii.me`)
- Deep-dive writeup (primary): https://raw.githubusercontent.com/sanand0/blog/main/posts/2025/mapscii-rendering.md
  (mirror: http://www.s-anand.net/blog/mapscii-rendering/ )
- Pipeline: Vector tiles -> parse protobuf -> RBush spatial index for viewport ->
  Web-Mercator transform -> rasterize to a high-res pixel canvas -> convert to braille ->
  emit ANSI color runs.
- Braille map identical to drawille: `[[0x1,0x8],[0x2,0x10],[0x4,0x20],[0x40,0x80]]`,
  glyph = `0x2800 + bits`. Flat buffer, one byte per cell's 8 dots.
- Pixel->cell: idx = `(x>>1) + (width>>1)*(y>>2)`; mask = `brailleMap[y&3][x&1]`;
  `pixelBuffer[idx] |= mask`; parallel `foregroundBuffer[idx] = color`.
- Lines: Bresenham callback per point -> setPixel. Polygons: earcut triangulation +
  scanline span fill (sort edge points by Y then X, fill horizontal runs).
- Color: xterm-256 (x256), ANSI runs emitted only on color change:
  `\x1B[38;5;{fg};48;5;{bg}m`, reset `\x1B[39;49m`. Cuts escape-sequence volume massively.

**Reproduce:** the "emit ANSI only when color changes" run-length trick is directly useful
for our renderer's output size. Bresenham+braille = crisp vector/plot drawing in a cell grid.

---

## 4. Demoscene / procedural effects (animated, cheap, look great)

### Fire effect (bash-on-fire) — classic heat propagation
- URL: https://bruxy.regnet.cz/web/linux/EN/bash-on-fire/
- Algorithm: bottom row randomly re-ignited each frame (`RANDOM%2*9` = cold 0 or hot 9).
  Shift whole buffer up one row, append new seed row. Each cell = average of 4 neighbors
  below it (below-left, below, below-right, two-below) -> integer /4 = built-in cooling.
  Heat value indexes an ANSI palette (space -> dim red `.`/`:` -> bright red `+` ->
  dim yellow -> bright yellow `U`/`W`). Redraw whole frame with cursor-home `\E[1;1f`.

### Plasma effect — sine-sum + palette cycling
- URL: https://en.wikipedia.org/wiki/Plasma_effect
- Per pixel: `v = sin(x/16)+sin(y/8)+sin((x+y)/16)+sin(sqrt(x*x+y*y)/8)` (range ~[-4,4]).
  x/y terms = banding, (x+y) = diagonals, sqrt = concentric ripples (organic look).
  Divisors = frequency (smaller = steeper gradient). Map to palette:
  `index = ((v+4)/8*255) & 255`. Animate by adding time `t` inside sines, or classic
  **palette cycling** `palette[(index+frame)&255]` (the 1988 VGA hardware-palette trick).

### Spinning ASCII donut (donut.c) — 3D + z-buffer + lighting on a char ramp
- URL: https://www.a1k0n.net/2011/07/20/donut-math.html
- Torus param by (theta, phi), rotated by animation angles A,B, perspective-projected
  `(x',y') = (K1*x/(K2+z), K1*y/(K2+z))`. Per-cell **z-buffer** stores 1/z; nearer 1/z wins.
  Luminance L = surface-normal . light(0,1,-1) = Ny - Nz. Map L>0 to ramp
  `.,-~:;=!*#$@` (12 chars, dark->bright). Demonstrates depth + shading in pure ASCII.

**Reproduce:** fire/plasma are perfect idle/loading backdrops for our TUI. Donut shows the
generic recipe: 3D geometry -> project -> z-buffer per cell -> luminance -> glyph ramp
(or, better, subcell blitter + color). Palette-cycling is a near-free animation technique.

---

## 5. CRT / retro post-processing aesthetic
- cool-retro-term: https://github.com/Swordfish90/cool-retro-term (mirror
  https://github.com/probonopd/cool-retro-term ). QML + GLSL (8.7% GLSL). Mimics cathode
  tube screens. Named profiles seen: Default Amber, Default Green, IBM DOS. Effects live in
  the QML/GLSL shader sources (scanlines, glow/bloom, curvature, jitter, flicker, burn-in) —
  README doesn't enumerate them; would need to read the shader files to catalog exactly.
- WebGL/xterm.js port (readable shader code, closer to our use): https://github.com/remojansen/cool-retro-term-webgl
- CRT beam simulator (real electron-beam sim): https://github.com/blurbusters/crt-beam-simulator
- CRT-Dusha (phosphor decay, Bayer dither, scanlines, RGB decay): https://github.com/Riskdiver/CRT-Dusha

**Reproduce (approximate in cell grid, no GPU):** scanline = dim every other row's bg;
phosphor persistence = blend previous frame's cell brightness (decay) into current;
amber/green monochrome palette mapping; subtle per-frame jitter of column offsets;
"glow" = spill a fraction of a bright cell's color into neighbors.

---

## 6. Classic ANSI/textmode art scene (aesthetic + glyph vocabulary)
- 16colo.rs — the archive of BBS-era artpacks since early 1990s: https://www.16colo.rs/
  (archive repo https://github.com/16colo-rs/16c ). SAUCE metadata, CP437, 16-color.
- Blocktronics (modern collective): http://www.blocktronics.org/
- Pablo Murad primer (what defines classic ANSI): https://ansi.murad.gg/ — CP437 supplies
  box-drawing, block shading (░▒▓█), lines, corners; 16-color discipline; SAUCE metadata.
- Editors / techniques:
  - PabloDraw: https://github.com/blocktronics/pablodraw (ANSI/ASCII/RIPscrip, multi-user)
  - Moebius: https://github.com/blocktronics/moebius ("half-block brush", modern editor)
  - AnsiDraw (browser): https://ansidraw.com/
- Block-ASCII tutorials (how artists shade with CP437 blocks): http://roysac.com/tutorial/blockasciitut-z0-eye.html ,
  http://roysac.com/tutorial/zO-FlyEagleTutorial.html
- ANSI escape-code reference (SGR, cursor, colors): https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797

**Reproduce:** the CP437 shade ramp `░▒▓█` + 16 colors is a compact, authentic shading
palette that works in one color per cell (no subcell trickery). Great for "retro" theme.

---

## 7. ASCII line-art archives (mono glyph art, figlet)
- asciiart.eu — ~11,000 works, categorized (Animals, Buildings, Logos, One-line, Borders,
  Dividers, Patterns...): https://www.asciiart.eu/ . Style = structural line art from
  `/ \ _ | ( )` chars, plus figlet-style banner text and tileable borders/dividers.
- Curated lists:
  - https://github.com/devtooligan/awesome-ascii-art (resources + example .txt files)
  - https://github.com/moul/awesome-ascii-art
  - https://github.com/jcubic/awesome-ascii  (libraries)
  - https://github.com/90dy/awesome-ascii  (games/tools)
- ascii.nvim (art as lua tables, ready to embed): https://github.com/MaximilianLloyd/ascii.nvim
- textmode.js (real-time dynamic ASCII graphics lib): https://www.creativeapplications.net/news/textmode-js-library-for-dynamic-ascii-art-text-graphics-with-real-time-rendering/

**Reproduce:** figlet-style banners, tileable borders/dividers, and one-line art are
directly usable as TUI chrome (headers, separators, splash screens).

---

## Quick technique -> where-to-look index
- Max spatial res, mono: **braille** (drawille, mapscii)
- Best color photos: **half-block U+2580** (2 truecolor px/cell)
- Balanced: **quadrant/sextant/octant** blitters (notcurses)
- Best-glyph matching + dither: **chafa** (DIN99d, Bayer/FS)
- Animated backdrops: **fire, plasma, donut** (procedural)
- Retro look: **cool-retro-term/webgl port** (scanline/glow/persistence)
- Authentic shading palette: **CP437 ░▒▓█ + 16 colors** (16colo.rs scene)
- Output efficiency: **ANSI run-length, emit escape only on color change** (mapscii)
