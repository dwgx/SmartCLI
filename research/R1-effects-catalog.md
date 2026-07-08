# R1 — Terminal Visual-Effect Tools: Landscape & Technique Catalog

> **Archived first-pass research** — superseded by [`../knowledge/sources/`](../knowledge/sources/); folded into [`../knowledge/effects/`](../knowledge/effects/README.md) + [`../knowledge/works/`](../knowledge/works/README.md). See [`README.md`](README.md). Kept for provenance.


Research date: 2026-07-07. Sources: live web_search via codex subagents + direct WebFetch of
upstream source (lolcat lol.rb, lodev cgtutor fire/plasma, roysac figfont spec, chafa/cava/toilet
GitHub, TTE docs/repo @ HEAD 7a91dd9). Codex stdout treated as data and cross-checked against
primary sources where possible.

Terminal model assumed throughout: a `W x H` grid of cells, each `{ch, fg_rgb, bg_rgb, attr}`.
Frame `t` = elapsed seconds or integer frame index.

## ANSI color primitives

- 24-bit truecolor: FG `\x1b[38;2;R;G;Bm`, BG `\x1b[48;2;R;G;Bm` (R,G,B 0..255). Reset `\x1b[0m`.
- 256-color: FG `\x1b[38;5;Nm`, BG `\x1b[48;5;Nm`.
  - 0..15 system; 16..231 = 6x6x6 cube `N = 16 + 36*r + 6*g + b` (r,g,b in 0..5, xterm component
    `0 if c==0 else 55+40*c`); 232..255 grayscale `gray = 8 + 10*(N-232)`.
- Cursor hide `\x1b[?25l`, show `\x1b[?25h`; alternate screen `\x1b[?1049h/l`; home `\x1b[H`;
  absolute move `\x1b[{row};{col}H`.
- Ref: https://github.com/fnky/ANSI.md

---

## PART A — Classic terminal animation tools (visual + core technique)

Sources: cmatrix https://github.com/abishekvashok/cmatrix • unimatrix https://github.com/will8211/unimatrix •
neo https://github.com/st3w/neo • cbonsai https://gitlab.com/jallbrit/cbonsai •
pipes.sh https://github.com/pipeseroni/pipes.sh • asciiquarium https://github.com/cmatsuoka/asciiquarium •
sl https://github.com/mtoyoda/sl

### cmatrix — Matrix digital rain
- Visual: green rain in alternating columns; occasional bright white heads, green trailing glyphs.
  Default uses printable ASCII-ish chars; `-c` uses half-width katakana `U+FF66..U+FF9D`.
- Technique: ncurses grid state. `matrix[LINES+1][COLS]` cell array plus per-column `length[]`,
  `spaces[]`, `updates[]`. Only every other column used (`j += 2`). Each active column shifts cell
  values DOWN each update, inserts a random glyph/space at top, marks one cell `is_head`, clears
  cells past the randomized stream length. Trail "fade" is NOT alpha — it is simulated by erasing
  tail cells to spaces plus bold/normal + white head. Random in-place glyph mutation ~`rand()%8==0`.
  Timing `napms(update*10)`.

### unimatrix — python/curses unicode rain
- Visual: unicode katakana-like rain, digits, matrix punctuation. Can mimic cmatrix (`-n -s 96 -l o`).
- Technique: per-column spawners + moving Node objects. A `Canvas` owns one `Column` per x. Each
  Column has a countdown timer, spawns alternating `writer` and `eraser` Nodes. Writer moves down
  drawing random chars; eraser follows drawing spaces (trail disappears). Writer may be white head;
  when it advances it repaints the previous head glyph green -> bright-head/green-tail. Char pick
  `chars[randint(0,len)]`. Colors = curses pairs (1 fg, 2 white head, 3 status). Delay `(100-speed)*10`.
  Async mode: each node speed 1..3, advances only when async clock % speed matches.

### neo — modern truecolor rain
- Visual: film-accurate; many droplets, half-width katakana default, uneven brightness, optional
  glitching chars, multiple droplets per column, 16/256/truecolor palettes.
- Technique: DROPLET simulation (not simple column shift). A `Cloud` manages pooled `Droplet`s +
  random char pool + per-position color map + per-cell glitch map. Each Droplet: column, head/tail
  positions, length, chars-per-sec, end line, linger. Per frame: advance `headPutLine` by
  `round(charsPerSec*elapsed)`, start advancing `tailPutLine` once head has traveled the droplet
  length, kill when tail catches head. Range-based draw: erase tail cells, draw only head-to-tail,
  skip unchanged middle. Head = max color pair + bold; tail = dim pair1 non-bold; middle random or
  gradient-shaded by distance from head. Glitch cells periodically brighten/dim/swap glyph. 60 FPS.

### cbonsai — procedural ASCII bonsai
- Visual: ASCII bonsai grows upward from a pot; trunk curves, shoots split L/R, dying branches bloom
  into leaves. Live mode = step-by-step.
- Technique: recursive STOCHASTIC branch growth (L-system-like but hand-coded, not grammar rewriting).
  `growTree()` -> `branch(..., trunk, lifeStart)` at bottom center. `branch()`: increment global
  branch counter, choose `(dx,dy)` from `setDeltas()` by branch type + age/life + multiplier, choose
  segment string via `chooseString()`, print, sleep (live), then RECURSE for continued growth or
  child shoots. Branch types: `trunk`, `shootLeft`, `shootRight`, `dying`, `dead`. Trunks fork into
  another trunk or alternating L/R shoots; near-dead branches spawn many dying/dead leaf calls.
  Glyphs: trunk `/~ \| /|\ |/`; shoots `\ \_ _/`; leaves default `&`. ncurses color pairs wood/leaf
  + bold bright variants. Live step ~0.03s.

### pipes.sh — random-walking colored pipes
- Visual: colored pipes crawl, turn randomly, wrap at edges; screen fills with connected box-drawing.
- Technique: random-walking agents. Each pipe: arrays `x[] y[] l[](cur dir) n[](next dir) v[](type)
  c[](color escape)`. Directions `0=up 1=right 2=down 3=left`. Each tick: move one cell in current
  dir, wrap modulo, optionally change color/type at edge, pick next dir (no 180 reversal), print glyph
  at index `old_dir*4 + new_dir` into a 16-char lookup string. Straight-vs-turn probability via `-s`
  (default mostly straight). Glyph sets (16 chars, transition table):
  - heavy `-t 0`: `┃┏ ┓┛━┓ ┗┃┛┗ ┏━` — straights `┃ ━`, corners `┏ ┓ ┗ ┛`
  - rounded `-t 1`: `│╭ ╮╯─╮ ╰│╯╰ ╭─`
  - double `-t 3`: `║╔ ╗╝═╗ ╚║╝╚ ╔═`
  - ascii `-t 4`: `|+ ++-+ +|++ +-`
  - custom `-t c<16 chars>`
  Render: direct ANSI `printf '\e[%d;%dH%s%s' row col color glyph`; colors `tput setaf`; alt screen +
  hidden cursor + `read -t` timing.

### asciiquarium — animated ASCII aquarium
- Visual: fish swim L/R, bubbles rise, seaweed waves, castle at bottom; occasional shark/whale/ship/
  monster/big-fish cross.
- Technique: sprite/entity animation via Perl `Term::Animation` over Curses. Each entity = multi-line
  ASCII sprite + optional color mask + depth. Engine moves entities by speed/direction, handles
  redraw/erase, layering (depth), collision, death callbacks, frame animation. Fish spawn count scales
  with terminal area; random sprite variant, y, speed ~0.25..2.25, depth, direction. Fish callbacks
  spawn bubbles (rise, die on collision). Sharks carry an invisible `teeth` overlay entity to kill
  small fish. Seaweed procedurally built from repeated `(` / ` )`, height 3..6, slow anim.

### sl — steam locomotive
- Visual: steam locomotive scrolls right-to-left. Variants D51/C51/long/flying/accident.
- Technique: fixed ASCII sprite frames + horizontal translation. Loop `x = COLS-1` decrement until
  off-screen. Each frame draw multi-line sprite at `(y,x)`, refresh, `usleep(40000)`. Wheel animation
  = 6-frame table indexed from `x` (wheels cycle as train moves). Smoke is stateful: static array of
  puffs (y/x/pattern/kind); every few columns erase old smoke, advance puffs up/right via `dy[]/dx[]`,
  draw larger smoke frames, insert new puff at funnel. `mvaddch`, clips negative x per char.

---

## PART B — Color / text rendering tools

### lolcat — rainbow gradient colorizer
- Visual: smooth per-char hue drift across each line, drifting line to line.
- Exact upstream formula (`lib/lolcat/lol.rb`, BSD):
  ```ruby
  red   = Math.sin(freq*i + 0)            * 127 + 128
  green = Math.sin(freq*i + 2*Math::PI/3) * 127 + 128
  blue  = Math.sin(freq*i + 4*Math::PI/3) * 127 + 128
  ```
  Three sines 120° apart (phases 0, 2π/3, 4π/3), amplitude 127, offset 128 -> `#RRGGBB`.
- Defaults (`cat.rb`): `freq = 0.1`, `spread = 3.0`.
- Position: per line `@os += 1`; per char `i_effective = @os + char_index/spread`. Larger spread =
  slower color change across chars; larger freq = faster cycling.
- Truecolor via `Paint.mode = 0xffffff` when `COLORTERM` contains `truecolor`/`24bit`, else 256.
- Source: https://github.com/busyloop/lolcat/blob/master/lib/lolcat/lol.rb , .../cat.rb

### chafa — image -> terminal art
- Visual: photos become colored glyph-cell art.
- Technique: resize image to cell-sized work cells; approximate each cell with a Unicode symbol +
  fg/bg colors minimizing coverage/color error.
- Modes & unicode ranges:
  - Half-block: `▀ U+2580` `▄ U+2584`; one cell = two vertical pixels (top=fg, bottom=bg for `▀`).
  - Block elements `U+2580..U+259F` (full `U+2588`, left `U+258C`, right `U+2590`, shades).
  - Braille `U+2800..U+28FF`: `cp = 0x2800 + bitmask`, 2x4 dot grid -> 8x8 coverage mask.
  - Sextant `U+1FB00..U+1FB3B` (Symbols for Legacy Computing): 2x3 subcells, `bit = y*2 + x`.
- Symbol matching: build a candidate bitmap from chosen fg/bg, shortlist by bitmap similarity, then
  score each candidate:
  ```
  error(symbol,fg,bg) = Σ_pixels color_distance(image[p], symbol_coverage[p] ? fg : bg)
  ```
  Keep min-error symbol/color pair. Works in RGB and DIN99d color spaces for better picking.
- Dithering: ordered (Bayer-like, default 16x16 texture), noise (blue-noise), diffusion
  (Floyd-Steinberg). Ordered/noise perturb channels pre-quantization: `c' = clamp(c+tex[x,y],0,255)`.
- Source: https://github.com/hpjansson/chafa (chafa-symbols.c, chafa-symbol-renderer.c, chafa-dither.c)

### figlet — ASCII banner text
- Visual: large ASCII banners from `.flf` FIGfont glyphs.
- FIGfont v2 header (single line): `flf2a<hardblank> height baseline max_length old_layout
  comment_lines print_direction full_layout codetag_count`. First 7 required; last 3 optional.
  - Signature `flf2a`; hardblank char (any non-space/CR/LF/null, conventionally `$`) renders as space
    but behaves as visible sub-char when fitting/smushing horizontally.
  - Each glyph = `height` rows; rows end with an endmark (commonly `@`); final row has two endmarks.
    Driver strips the last block of consecutive equal chars per line to determine width.
- Layout modes per axis: full-width | fitting (kerning) | smushing.
- Horizontal smushing rules (additive bit values):
  - 1 Equal Character (identical sub-chars merge, excludes hardblanks)
  - 2 Underscore (`_` yields to `|/[]{}()<>`)
  - 4 Hierarchy (class order `|` < `/\` < `[]` < `{}` < `()` < `<>`, later wins)
  - 8 Opposite Pair (opposing brackets/braces/parens -> `|`)
  - 16 Big X (`/\`->`|`, `\/`->`Y`, `><`->`X`)
  - 32 Hardblank (two hardblanks -> one)
  - Vertical rules: 256, 512, 1024, 2048, 4096.
  - Full_Layout defaults: 64 horiz fitting, 128 horiz smushing, 8192 vert fitting, 16384 vert smushing.
  - `smushamt()` computes max overlap; `smushem(lch,rch)` merges or returns `\0`.
- Source: https://github.com/cmatsuoka/figlet , spec http://roysac.com/learn/figfont.txt

### toilet — figlet-like + color/filters (libcaca)
- Visual: FIGfont banners with unicode, color fonts, filters.
- Technique: delegates FIGfont render to libcaca (`caca_canvas_set_figfont`, `caca_put_figchar`,
  `caca_flush_figlet`), then applies canvas filters. Filters differ from lolcat:
  - Rainbow: fixed 6-color ANSI palette [LIGHTMAGENTA, LIGHTRED, YELLOW, LIGHTGREEN, LIGHTCYAN,
    LIGHTBLUE], `color = rainbow[(x/2 + y + lines) % 6]`.
  - Metal: 4-color [LIGHTBLUE, BLUE, LIGHTGRAY, DARKGRAY], `i = ((lines + y + x/8)/2) % 4`.
  - Others: crop, flip, flop, rotate, left, right, border.
- Source: https://github.com/cacalabs/toilet (src/filter.c, src/figlet.c)

### cava — console audio visualizer
- Visual: real-time spectrum bars, optional vertical/horizontal gradient.
- Technique: sample audio -> Hann window -> FFTW real FFT -> aggregate bins into log-spaced bands ->
  smooth -> scale to cell heights -> draw block bars.
  - Hann window `w[i] = 0.5*(1 - cos(2πi/(N-1)))`, `xw[i]=x[i]*w[i]`. Buffer starts 512.
  - Magnitude `mag[k] = sqrt(re[k]^2 + im[k]^2)`.
  - Log band cutoffs:
    ```
    fc = log10(lower/upper) / (1/(bars+1) - 1)
    coeff(n) = -fc + ((n+1)/(bars+1))*fc
    cutoff[n] = upper * 10^coeff(n)
    bin = (cutoff/(sample_rate/2)) * (FFT_size/2)
    ```
  - Band value `band[n] = eq[n] * Σ_{k=lo..hi} mag[k]`.
  - Gravity falloff: `gravity_mod = (66/framerate)^2.5 * 2 / noise_reduction`;
    `out[n] = peak[n]*(1 - fall[n]^2*gravity_mod)`, `fall[n] += 0.028`.
  - Bars quantized to eighths: full `U+2588`, fractional `U+2581..U+2587`. `full=bars/8, frag=bars%8`.
  - Gradient: parse `#RRGGBB`, per-channel linear lerp `C = C0 + (C1-C0)*t`, emit truecolor.
- Source: https://github.com/karlstav/cava (cavacore.c, cava.c, output/terminal_noncurses.c)

---

## PART C — terminaltexteffects (TTE) — 37 effects @ HEAD 7a91dd9

Source: https://github.com/ChrisBuilds/terminaltexteffects , docs https://chrisbuilds.github.io/terminaltexteffects/

| Effect | Visual + core technique |
|---|---|
| Beams | Row/col light beams sweep canvas; grouped row/col scenes w/ beam-symbol gradients, diagonal final brighten wipe. |
| BinaryPath | Each char decomposes into 8 binary glyphs traveling off-canvas along orthogonal waypoint paths, collapse to glyph, diagonal brighten. |
| Blackhole | Text->stars, rotating black-hole ring forms, non-ring stars ease exponentially to center, ring collapses, explode outward, cool to final. |
| BouncyBalls | Chars fall as ball symbols via vertical paths w/ bounce easing, resolve through color gradient to glyphs. |
| Bubbles | Char groups form circular bubbles, float down via anchor path, pop on circular paths, return to input coords (expo easing). |
| Burn | Text ignites in staggered groups, cycles flame colors + optional smoke particles, cools/reveals final gradient. |
| ColorShift | Static text shifts through gradient colors; looping per-char scenes with offset gradient spectra. |
| Crumble | Chars weaken, fall as dust (bounce), vacuumed up along Bezier paths, reset to input coords, strengthen to final color. |
| Decrypt | Movie decryption: ciphertext types in, mutates random symbols/colors, resolves to plaintext (typed reveal queues + randomized scenes). |
| ErrorCorrect | % of chars start swapped/wrong (error color), pairs swap back with delayed correction + gradient. |
| Expand | Text compressed at center, each char follows path center->input coord with configurable easing. |
| Fireworks | Char shells launch, explode into radial bursts (circular coords), fall/settle into text + gradient scenes. |
| Highlight | Bright band scans visible text; grouped bands temporarily brightness-adjusted then restored. |
| LaserEtch | Laser sweep etches chars by row/col/diagonal order; moving etch groups, bright etch colors, cooling scenes. |
| Matrix | Digital rain columns fall w/ random symbols/colors, fill canvas, resolve to text (per-column rain queues, trim/drop, resolve). |
| MiddleOut | Text appears squeezed through middle line/col then expands; two-stage paths center-axis->final. |
| OrbittingVolley | Four orbiting launchers fire volleys inward; launcher circular paths + char paths launcher->input. |
| Overflow | Text copies overflow/scroll upward like scrollback before final text remains (row cycling + overflow gradients). |
| Pour | Chars pour from a side/up/down like liquid, overshoot/backtrack with gaps, settle (grouped directional eased paths). |
| Print | Print head moves typewriter-style, reveals chars in order w/ carriage returns (helper print-head char + row reveal). |
| Rain | Chars fall as raindrops, resolve where they land (start above canvas, randomized speed/symbol/color, gradient). |
| RandomSequence | Chars appear in random order (shuffled queue, reveal % per tick, final gradient). |
| Rings | Chars form concentric rings, spin, disperse, resolve (circular coord gen + ring rotation + return paths). |
| Scattered | Chars start scattered across/off canvas, fly home (random start coords + eased paths). |
| Slice | Text sliced vertical/horizontal/diagonal, slides into place (grouped slice paths offset->final). |
| Slide | Rows/cols/diagonals slide in from outside; grouped activation w/ gap, direction reversal, optional merge. |
| Smoke | Smoke floods canvas recoloring chars (spanning tree + BFS traversal, smoke-symbol scenes, paint gradient). |
| Spotlights | Moving spotlights search dim text then converge/reveal; brightness = f(distance to beam center) falloff per frame. |
| Spray | Chars spray from origin, land in positions (randomized speed paths origin->input, gradient reveal). |
| Swarm | Chars swarm in clusters around random areas then assemble (swarm grouping, shared/random waypoints, flash scenes). |
| Sweep | First sweep reveals gray text, reverse sweep colors it (grouped sweeps, SequenceEaser(in_out_circ), two shimmer scenes). |
| SynthGrid | Retro synth grid animates through text then text resolves (grid-line helper chars + gradient, separate final gradients). |
| Thunderstorm | Rain falls, lightning branches strike, sparks, text flashes/glows/fades (particle pools, strike helpers, branching paths, timed phases). |
| Unstable | Text destabilizes, explodes outward, reassembles (per-char explosion paths to random/off positions, unstable color, reassembly). |
| VHSTape | VHS glitch: lines shift horizontally, RGB split, noise, final redraw (row glitch/restore paths, snow scenes, glitch waves). |
| Waves | Waves pass through text temporarily replacing symbols/colors (grouped wavefronts activate symbol-gradient scenes in sequence). |
| Wipe | Directional wipe reveal; grouped chars activate in configured order w/ delay + final gradient. |

### TTE engine model (reusable architecture)
- `EffectCharacter`: one glyph; stores `input_symbol`, `input_coord`, visibility, render `layer`,
  `motion`, `animation`, neighbor/link metadata, `EventHandler`. Per tick: `motion.move()` then
  `animation.step_animation()`.
- `Motion`/`Path`/`Waypoint`: named paths. A Path = ordered waypoints + optional Bezier controls +
  speed + easing + hold + loop + layer. Per frame:
  ```
  step += 1; p = step/max_steps
  distance = ease(p) * total_distance
  pick segment containing distance; local_t = dist_within_segment / segment.distance
  coord = line(start,end,local_t) OR bezier(start,controls,end,local_t)
  ```
  Line lerp `x=(1-t)x0+t*x1, y=(1-t)y0+t*y1`; Bezier = De Casteljau. Path length uses Euclidean
  distance, often DOUBLING the row delta to compensate terminal cell aspect ratio (cells ~2x tall).
- `Easing`: `0..1 -> 0..1`; sine/quad/cubic/quart/quint/expo/circ/back/elastic/bounce + custom cubic
  Bezier. E.g. `out_quad(t)=1-(1-t)^2`, `in_out_sine(t)=-(cos(pi*t)-1)/2`.
- `Scene`: sequence of `Frame(CharacterVisual, duration)`; can loop, ease frame index, or sync to
  motion by path step/distance. Frame = symbol + fg/bg + ANSI modes. Path/scene completion fires
  events -> activate another scene/path, set layer/coord, reset appearance, callback.
- `Gradient`: Color stops -> spectrum by integer RGB lerp. For 2 colors, n steps:
  `c_i = c0 + floor((c1-c0)/n)*i`. Mappings: vertical, horizontal, radial (norm dist from center),
  diagonal (weighted row/col fraction).
- `Canvas`/`Terminal`: text parsed to EffectCharacters on 1-based grid. Canvas tracks bounds, text
  bounds, center, random coords, fill chars, grouping/sorting. Per frame: build 2D space buffer, sort
  visible chars by layer, write formatted ANSI symbol at `current_coord + canvas_offset`, join rows.

---

## PART D — Reusable effect algorithms from blogs/demoscene (with formulas)

### 1. Decrypt / text-scramble reveal
Per-char start & lock frame; before lock show random glyphs, after lock show final.
```
glyphs = "ABC...Z0-9#$%&*+-/<>?[]{}"
start[i] = base_delay + i*stagger + rand(0,jitter)
lock[i]  = start[i] + rand(min_scramble, max_scramble)
per frame f, per i:
  f<start[i]        -> " "
  f<lock[i]         -> if f%refresh==0: scratch[i]=rand(glyphs); out=scratch[i]
  else              -> final[i]
```
Variant: probabilistic lock `p=smoothstep(start,end,t); rand<p ? final : random`.
Refs: GSAP ScrambleText https://gsap.com/docs/v3/Plugins/ScrambleTextPlugin/ ; TTE Decrypt.

### 2. Typewriter reveal
`n = floor(t*chars_per_sec); visible = final[0:n]`. Blink cursor `_` at blink_hz. Natural typing:
per-char delay 20-80ms, +120-300ms after punctuation, +200-500ms after newline.
Ref: TTE Print; https://css-tricks.com/snippets/css/typewriter-effect/

### 3. Glitch
- Char corruption: `if rand<rate: ch=rand("█▓▒░#@$%&?!/\\01"); fg=rand([white,red,cyan,green])`.
- Row displacement: `if rand<row_chance: dx=rand(-max,max); row_out[x]=row_in[(x-dx)%W]`.
- Block displacement: copy random block to offset position.
- RGB split: render red shifted x-1, green normal, blue shifted x+1; single-cell blend by max channel.
- Jitter: `screen_x = x + rand(-1,1) w/ prob jitter_p`, `screen_y` at prob jitter_p/4.
Refs: TTE VHSTape; https://aleclownes.com/2017/02/01/crt-display.html

### 4. CRT
- Scanlines: `scan = 1.0 if y%2==0 else 0.55; fg *= scan`.
- Phosphor mask (pixel-level): `mask(x)=[1.10,0.85,1.05][x%3]; rgb*=mask`.
- Glow: `glow[y][x]=0.40*src + 0.12*(4-neighbors) + 0.06*diagonals; final=base+strength*glow`.
- Flicker: `flicker(t)=0.96 + 0.04*noise(frame) + 0.02*sin(2π*59.94*t); rgb*=flicker`.
- Curvature (if pixel control): `nx=2x/W-1, ny=2y/H-1, r2=nx²+ny²; u=nx(1+k*r2), v=ny(1+k*r2)`.
  Pure terminal approx = edge vignette `1 - strength*(nx²+ny²)`.
Refs: https://aleclownes.com/2017/02/01/crt-display.html , https://github.com/Swordfish90/cool-retro-term

### 5. Scanline sweep
`sweep_y = (t*speed) mod (H+band) - band`; per cell `d=abs(y-sweep_y); boost=exp(-d²/(2σ²));
fg=base*(1+boost*1.5); bold if d<0.5`. Trailing fade `clamp(1-(y-sweep_y)/trail_len,0,1)`.
Ref: TTE Sweep/Highlight.

### 6. Sparkle / shimmer
Per frame spawn N random visible cells with TTL 3..10 frames; `a=ttl/max; fg=lerp(base,white,a);
ch=rand(["*","+",".","·","✦"]) or original; ttl--`. Deterministic wave: `step(0.97,
noise(x*12.9898 + y*78.233 + floor(t*fps)*37.719))`.
Ref: TTE Beams/Sweep.

### 7. Wipe / slide transitions
Assign each cell a reveal rank, reveal cells with rank <= frontier.
```
left->right:   rank=x        right->left: rank=W-1-x
top->bottom:   rank=y        bottom->top: rank=H-1-y
diag TL-BR:    rank=x+y      diag BL-TR:  rank=x+(H-1-y)
center-out:    rank=|x-cx|+|y-cy|         outside-in: maxdist - that
front = t*speed; visible if rank<=front; edge if front-edge_w<rank<=front
```
Slide-in: `start=rank*stagger; p=clamp((t-start)/dur,0,1); e=ease_out_quad(p);
draw_x=round(lerp(from_x, x, e))` (from_x = -W or 2W).
Refs: TTE Wipe, TTE Slide.

### 8. Fire (demoscene classic)
Bottom row seeded random every frame; each cell above = blend of cells below minus cooling.
Lode's shipped divisor form (`* 32 / 129` ≈ /4.03):
```
fire[H-1][x] = rand(0..255)                      # reseed every frame
for y = 0..H-2, x:
  sum = fire[y+1][(x-1+W)%W] + fire[y+1][x] + fire[y+1][(x+1)%W] + fire[y+2][x]
  fire[y][x] = sum * 32 / 129                     # /4 => rises forever, /5 => dies fast
```
Palette: HSL hue 0->85 (red->yellow), sat max, lightness dark->bright; 256-entry LUT indexed by heat.
Terminal char ramp `" .:-=+*#%@"[floor(heat/256*len)]`, fg=palette[heat].
Refs: https://lodev.org/cgtutor/fire.html , https://www.hanshq.net/fire.html

### 9. Plasma
```
v = 128 + 128*sin(x/16) + 128 + 128*sin(y/8)
  + 128 + 128*sin((x+y)/16) + 128 + 128*sin(sqrt(x²+y²)/8)
color = int(v)/4                 # /num_terms -> back to 0..255
```
Or normalized form `v = Σ sin(...+t*p); normalized=(v+4)/8; idx=floor(normalized*(len-1))`.
Animate cheaply by palette-shift: `buffer=palette[(plasma[y][x]+int(t/10))%256]` (looping palette,
no seam if HSV rainbow). Or move shape by injecting `t` into sine args (slower). Terminal: shade ramp
`" .:-=+*#%@"`, fg=hsv((normalized+t*0.05)%1, 0.8, 1.0). Precompute sin_x[], sin_y[], dist[][].
Refs: https://lodev.org/cgtutor/plasma.html , https://rosettacode.org/wiki/Plasma_effect

### 10. Starfield (3D)
```
star: x,y in [-1,1], z in [z_near,z_far], speed 0.2..1.5
per frame: z -= speed*dt; if z<=z_near reset z=z_far
  sx = cx + (x/z)*focal; sy = cy + (y/z)*focal
  brightness = clamp(1 - z/z_far, 0, 1); ch = choose(".+*✦", brightness)
```
Warp trails: draw line from projected(z+speed*dt) to current. Cheap 2D layered variant:
speed per layer `0.2 + layer*0.8`, brightness = layer/num_layers.
Refs: https://www.sunshine2k.de/coding/javascript/graphiceffects/02_starfield/ , kirupa.

### 11. Rainbow / gradient waves
Hue wave `h=fract(base + x/period_x + y/period_y - t*speed); rgb=hsv(h,sat,val)`.
Sine brightness `phase=2π(x/λ + y*diag - t*speed); brightness=0.65+0.35*sin(phase)`.
Gradient interp over stops `[red,yellow,green,cyan,blue,magenta]`: `u=fract((x+y*diag)/period -
t*speed); seg=floor(u*len); rgb=lerp(stops[seg], stops[(seg+1)%len], fract(u*len))`.
Wave glyphs `["▁","▂","▃","▄","▅","▆","▇","█","▇",...]` indexed by `fract(x/λ - t*speed)*len`.
Refs: lolcat; https://github.com/bokub/gradient-string ; TTE Waves.
