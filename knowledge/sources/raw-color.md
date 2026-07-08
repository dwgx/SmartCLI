# Terminal Color & Typography — Authoritative Sources (raw)

Compiled 2026-07-08. Every fact carries a source URL. Codex live-search runs 1-2
(ANSI/256/downgrade + interpolation/lolcat/palettes) succeeded; run 3 codex account
hit a 403 credit error, so half-block/wcwidth/figlet/box-drawing were sourced via
direct WebFetch of the canonical specs/docs.

---

## 1. ANSI truecolor (24-bit)

- Foreground: `ESC[38;2;R;G;Bm`  Background: `ESC[48;2;R;G;Bm`  (R/G/B decimal 0..255).
  Source: xterm ctlseqs https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
  Source: https://en.wikipedia.org/wiki/ANSI_escape_code#24-bit
- xterm documents `Ps = 38 ; 2 ; Pr ; Pg ; Pb` (fg) and `48 ; 2 ; ...` (bg).
  Source: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
- ECMA-48 reserves SGR 38/48 for foreground/background colour per ISO 8613-6 / ITU T.416.
  Source: https://ecma-international.org/wp-content/uploads/ECMA-48_5th_edition_june_1991.pdf
- Detection convention `COLORTERM=truecolor` or `COLORTERM=24bit` (VTE, Konsole, iTerm2 set `truecolor`).
  Source: https://github.com/termstandard/colors#checking-for-colorterm

## 2. 256-color mode (8-bit)

- Indexed fg `ESC[38;5;Nm`, bg `ESC[48;5;Nm`.
  Source: https://en.wikipedia.org/wiki/ANSI_escape_code#8-bit
- Cube indices 16..231: `index = 16 + 36*r + 6*g + b`, r,g,b in 0..5.
  Source: https://en.wikipedia.org/wiki/ANSI_escape_code#8-bit
- Cube channel levels `{0,95,135,175,215,255}` = hex `{00,5f,87,af,d7,ff}`.
  Equivalent: `component = coord==0 ? 0 : coord*40 + 55`.
  Source: https://github.com/ThomasDickey/xterm-snapshots/blob/master/256colres.h
- Grayscale ramp indices 232..255 (24 steps): `gray = 8 + 10*i`, i in 0..23 → 8,18,...,238.
  Source: https://en.wikipedia.org/wiki/ANSI_escape_code#8-bit ; https://github.com/tmux/tmux/blob/master/colour.c

## 3. Nearest-color downgrade (24-bit → 256), tmux colour.c

- Algorithm (`colour_find_rgb`): quantize RGB to nearest 6x6x6 cube candidate AND nearest
  grayscale candidate, then pick whichever has smaller squared Euclidean distance.
  Source: https://github.com/tmux/tmux/blob/master/colour.c
- Cube levels `q2c = {0x00,0x5f,0x87,0xaf,0xd7,0xff}`.
- Cube quantizer `colour_to_6cube(v)`: `v<48 → 0`; `v<114 → 1`; else `(v-35)/40`.
  Ranges: 0..47→0, 48..114→1, 115..154→2, 155..194→3, 195..234→4, 235..255→5.
- Cube index: `16 + 36*qr + 6*qg + qb`.
- Grayscale candidate: `grey_avg=(r+g+b)/3`; if `grey_avg>238` idx=23 else `(grey_avg-3)/10`;
  `grey = 8 + 10*idx`, palette index `232+idx`.
- Distance metric `colour_dist_sq`: unweighted `(R-r)^2 + (G-g)^2 + (B-b)^2`.
  Source (all above): https://github.com/tmux/tmux/blob/master/colour.c

## 4. Linear RGB interpolation & multi-stop gradients

- Per-channel lerp: `c = c0 + t*(c1-c0)`, applied independently to R,G,B.
  Source: https://fgiesen.wordpress.com/2012/08/15/linear-interpolation-past-present-and-future/
- Multi-stop: find interval [x0,x1] containing position x, local `t=(x-x0)/(x1-x0)`, lerp channels.
  Source: https://www.w3.org/TR/css-color-4/#interpolation
- sRGB vs linear-light: sRGB is gamma-encoded; lerping encoded values ≠ lerping light intensity.
  Source: https://www.w3.org/TR/css-color-4/#predefined-sRGB , #predefined-sRGB-linear
- sRGB→linear: `linear = s/12.92` if `s<=0.04045` else `((s+0.055)/1.055)^2.4`.
- linear→sRGB: `s = 12.92*linear` if `linear<=0.0031308` else `1.055*linear^(1/2.4) - 0.055`.
  Source: https://www.w3.org/TR/css-color-4/#color-conversion-code

## 5. HSV rainbow cycling — lolcat (busyloop/lolcat)

- `rainbow(freq,i)` from lib/lolcat/lol.rb:
  red   = sin(freq*i + 0)*127 + 128
  green = sin(freq*i + 2π/3)*127 + 128
  blue  = sin(freq*i + 4π/3)*127 + 128
  Source: https://github.com/busyloop/lolcat/blob/master/lib/lolcat/lol.rb
- Position for plain print: `rainbow(freq, @os + i/spread)`.
- Defaults: `--freq 0.1`, `--spread 3.0`.
  Source: https://github.com/busyloop/lolcat/blob/master/man/lolcat.6

## 6. Curated palettes (exact hex)

### viridis (matplotlib / BIDS)
- Anchor stops: `#440154 #414487 #2A788E #22A884 #7AD151 #FDE725`.
- Data endpoints: [0.267004,0.004874,0.329415]→#440154 ; [0.993248,0.906157,0.143936]→#FDE725.
  Source: https://github.com/matplotlib/matplotlib/blob/main/lib/matplotlib/_cm_listed.py ; https://github.com/BIDS/colormap

### Solarized (Ethan Schoonover)
base03 #002b36  base02 #073642  base01 #586e75  base00 #657b83
base0 #839496   base1 #93a1a1   base2 #eee8d5   base3 #fdf6e3
yellow #b58900  orange #cb4b16  red #dc322f     magenta #d33682
violet #6c71c4  blue #268bd2    cyan #2aa198    green #859900
  Source: https://ethanschoonover.com/solarized/ ; https://github.com/altercation/solarized

### SynthWave '84 (robb0wen/synthwave-vscode)
`#171520 #241b2f #262335 #2a2139 #463465 #614D85 #03edf9 #36f9f6
 #72f1b8 #ff7edb #f97e72 #fe4450 #fede5d #f3e70f #848bbd #ffffff`
  Source: https://github.com/robb0wen/synthwave-vscode/blob/master/themes/synthwave-color-theme.json

## 7. Image → ANSI via half-block (chafa)

- Half-block technique: one cell shows two vertical pixels — set fg = top pixel color,
  bg = bottom pixel color, print U+2580 UPPER HALF BLOCK; doubles vertical resolution.
  chafa: "You can get fair results by using only U+2580 (upper half block)"; enable with
  `chafa --symbols vhalf`. Chafa uses a wider symbol set by default for better quality.
  Source: https://hpjansson.org/chafa/
- chafa `--symbols` classes: all, none, space, solid, stipple, block, border, diagonal,
  dot, quad, half, hhalf, vhalf, inverted, braille, technical, geometric, ascii, legacy,
  sextant, wedge, wide, narrow. Default set: block+border+space-wide-inverted.
  Sextants (U+1FB00 block) and quads subdivide the cell further than half-blocks.
  Source: https://hpjansson.org/chafa/man/ ; repo https://github.com/hpjansson/chafa

## 8. wcwidth / East Asian Width (Markus Kuhn wcwidth.c, UAX #11)

- Canonical impl: https://www.cl.cam.ac.uk/~mgk25/ucs/wcwidth.c
- UAX #11 East Asian Width: https://www.unicode.org/reports/tr11/
- Width 0 (combining): general categories Mn, Me, Cf; excludes soft hyphen U+00AD;
  adds Hangul Jamo medial/final U+1160..U+11FF and U+200B. Table begins
  {0x0300,0x036F},{0x0483,0x0486},{0x0488,0x0489}... through variation selectors
  U+FE00..U+FE0F, U+FEFF, ending {0xE0100,0xE01EF}.
- Width -1: C0/C1 controls + DEL — `ucs<32 || (ucs>=0x7f && ucs<0xa0)`.
- Width 2 (wide/fullwidth) — `ucs>=0x1100` and one of:
  0x1100..0x115F (Hangul Jamo init); U+2329,U+232A; 0x2E80..0xA4CF except 0x303F;
  0xAC00..0xD7A3 (Hangul syllables); 0xF900..0xFAFF (CJK compat ideographs);
  0xFE10..0xFE19 (vertical forms); 0xFE30..0xFE6F (CJK compat forms);
  0xFF00..0xFF60 (fullwidth forms); 0xFFE0..0xFFE6;
  0x20000..0x2FFFD and 0x30000..0x3FFFD (supplementary ideographic planes).
  NOTE: wide test uses 0xFE30..0xFE6F (not ..4F), and CJK starts at 0x2E80 with 0x303F excluded.
- `mk_wcwidth_cjk` variant treats East Asian Ambiguous (Greek, Cyrillic, box drawing, etc.)
  as width 2 via a separate ambiguous[] table.
  Source: https://www.cl.cam.ac.uk/~mgk25/ucs/wcwidth.c

## 9. FIGlet .flf font format & FIGfont spec

- Spec: http://www.figlet.org/figfont.txt (mirror: https://github.com/cmatsuoka/figlet/blob/master/figfont.txt)
- Header line (example `flf2a$ 6 5 20 15 3 0 143 229`), fields in order:
  1. Signature+Hardblank: first 5 chars "flf2a", 6th char = hardblank
  2. Height (sub-chars per FIGchar)
  3. Baseline (lines from baseline to top of tallest FIGchar)
  4. Max_Length (max line length describing a FIGchar)
  5. Old_Layout (-1..63, legacy)
  6. Comment_Lines (# of comment lines)
  7. Print_Direction (0 = L→R, 1 = R→L)  [optional]
  8. Full_Layout (0..32767, layout + smushing rules)  [optional]
  9. Codetag_Count (total chars minus 102)  [optional]
  First 7 required; last 3 optional but recommended.
- Hardblank: renders as space but acts as a visible sub-char when fitting/smushing horizontally
  (keeps chars apart, builds the space glyph, prevents illegible over-smushing like C→G).
  Convention `$`; any char except space/CR/newline/null. Treated as normal blank vertically.
- Layout modes: Full Size (full width) → Fitting/Kerning (move until touching) →
  Smushing (overlap one step; controlled=designer rules, or universal=later sub-char wins).
- Horizontal smushing rules (code values):
  1 Equal Character (identical merge; not hardblanks)
  2 Underscore (`_` replaced by `| / \ [ ] { } ( ) < >`)
  4 Hierarchy (classes `|`,`/\`,`[]`,`{}`,`()`,`<>`; latter wins)
  8 Opposite Pair (opposing brackets/braces/parens → `|`)
  16 Big X (`/\`→`|`, `\/`→`Y`, `><`→`X`)
  32 Hardblank (two hardblanks → one)
  Five vertical rules (values 256..4096) mirror these plus horizontal-line + vertical super-smushing.
  Source: http://www.figlet.org/figfont.txt

## 10. Unicode box-drawing block U+2500..U+257F

- Block: Box Drawing, BMP, U+2500..U+257F, 128 characters (added Unicode 1.1, 1993).
  Source: https://www.unicode.org/charts/PDF/U2500.pdf ; https://en.wikipedia.org/wiki/Box-drawing_characters
  Block ref: https://www.compart.com/en/unicode/block/U+2500

- Single (light): ─ U+2500  │ U+2502  ┌ U+250C  ┐ U+2510  └ U+2514  ┘ U+2518
  Junctions: ├ U+251C  ┤ U+2524  ┬ U+252C  ┴ U+2534  ┼ U+253C
- Double: ═ U+2550  ║ U+2551  ╔ U+2554  ╗ U+2557  ╚ U+255A  ╝ U+255D
  Junctions: ╠ U+2560  ╣ U+2563  ╦ U+2566  ╩ U+2569  ╬ U+256C
- Heavy: ━ U+2501  ┃ U+2503  ┏ U+250F  ┓ U+2513  ┗ U+2517  ┛ U+251B
  Junctions: ┣ U+2523  ┫ U+252B  ┳ U+2533  ┻ U+253B  ╋ U+254B
- Rounded (light arc): ╭ U+256D  ╮ U+256E  ╰ U+2570  ╯ U+256F
  Source: https://en.wikipedia.org/wiki/Box-drawing_characters ; codepoints.net/U+256D , /U+256F
- Auto-connecting borders: a junction glyph encodes which of the 4 edges (up/down/left/right)
  and their weights (light/heavy/double) are present. To render a grid, compute each cell's
  edge bitmask (which neighbors connect + weight) and map it to the matching glyph — e.g. a
  cell with left+right = ─, +down = ┬, all four = ┼. Mixed-weight junctions exist (U+251C..U+254B
  range covers light/heavy combinations, e.g. ┝ U+251D light-up/down heavy-right).
