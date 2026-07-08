# Terminal Visual-Art — Deep-Dive Technique Extraction

Survey date: 2026-07-08. Every entry primary-source-verified via WebFetch of the actual repo/blog
(source .c/.rb/.py/.rs files where fetchable, README where source not exposed).
Focus: the REAL rendering method — algorithm, character ramp, ANSI trick, animation loop —
plus what SmartCLI's CellField/SubcellRaster kernel can borrow and the KB entry it maps to.

Kernel reminder (see [[rendering-model]]): 4 primitives — CellField (S(x,y,t)->Sample),
SubcellRaster (half/quadrant/braille sub-pixels), BoxJunction (edge-weight glyph lookup),
ColorModel (truecolor SGR + honest degrade). ASPECT=2.0 (cells ~2x tall as wide).

---

## 1. donut.c — spinning ASCII torus  ★ full math
- URL: https://www.a1k0n.net/2011/07/20/donut-math.html (Andy Sloane)
- REAL TECHNIQUE — no raytracing, just parametric surface + normal-dot-light:
  - Torus = circle radius R1=1 centered at (R2=2,0,0), swept by theta, then revolved around y by phi.
  - Two spin angles A (about x), B (about z), incremented per frame: `A += 0.04; B += 0.02`.
  - Fully multiplied-out point:
    - `x = (R2+R1cosθ)(cosB cosφ + sinA sinB sinφ) − R1 cosA sinB sinθ`
    - `y = (R2+R1cosθ)(cosφ sinB − cosB sinA sinφ) + R1 cosA cosB sinθ`
    - `z = cosA(R2+R1cosθ)sinφ + R1 sinA sinθ`
  - Perspective projection: `ooz = 1/z` (one-over-z). Screen: `xp = W/2 + K1·ooz·x`, `yp = H/2 − K1·ooz·y` (y negated: 3D up = screen down). `K1 = W·K2·3/(8·(R1+R2))`, K2=5.
  - Z-BUFFER TRICK: store `ooz` not z. `ooz=0` = infinite depth so buffer pre-inits to 0; plot only if `ooz > zbuffer[xp][yp]`. Also cheaper (multiply by ooz twice vs divide twice).
  - LUMINANCE = surface-normal · light. Normal = same rotation applied to unit point (cosθ,sinθ,0). Light dir (0,1,−1) → `L = Ny − Nz`, range −√2..+√2. Skip if L≤0 (faces away).
  - RAMP: `.,-~:;=!*#$@` (12 chars, dim→bright). Index = `L*8` → 0..11 (8√2≈11.3).
  - Loop spacing: θ step 0.07, φ step 0.02, both 0..2π. Frame emit: `\x1b[H` then print rows.
- BORROW: exact donut is a `CellField` sampled over (θ,φ) with a per-cell z-buffer max-composite; the L*8 index is [[ascii-luminance-ramp]]. y-negate + ASPECT interplay: K1 already bakes aspect via the 3/8 width term; SmartCLI should still y-correct any circular metric.
- KB: [[donut-torus]] (exact), [[perspective-projection]], [[rotation-matrix]], [[ascii-luminance-ramp]].

## 2. lolcat — rainbow colorizer  ★ exact algorithm
- URL: https://github.com/busyloop/lolcat (verified lib/lolcat/lol.rb)
- REAL TECHNIQUE — 3 phase-offset sine waves = the color wheel:
  - `red = sin(freq·i + 0)·127+128`, `green = sin(freq·i + 2π/3)·127+128`, `blue = sin(freq·i + 4π/3)·127+128`. Offsets 0/120°/240° trace hue; `·127+128` maps [−1,1]→[1,255].
  - Per char: `color = rainbow(freq, os + i/spread)`. freq = hue cycle speed; spread = chars per hue step (stretch); os = seed offset. Per line `os += 1` → diagonal gradient; animate mode advances os over time.
  - EMIT: truecolor `38;2;r;g;b` when `COLORTERM ∈ {truecolor,24bit}` (Paint.mode=0xffffff), else nearest 256 `38;5;n`. Reset FG `\e[39m` (or BG `\e[49m` in invert mode).
- BORROW: this IS the SmartCLI hue-cycle field — a 1-line `CellField` where phase = f(x,y,t). Reuse for gradient dividers, animated banners, ultracode glow tint. The 120° sine trio is cheaper + smoother than HSV→RGB.
- KB: [[hsv-cycling-lolcat]] (exact), [[truecolor-24bit]], [[color-interpolation]], [[ansi-sgr-color]].

## 3. cbonsai — procedural bonsai  ★ full recursion
- URL: https://gitlab.com/jallbrit/cbonsai (verified cbonsai.c). C + ncurses + panels.
- REAL TECHNIQUE — recursive `branch(y,x,type,life)`, `while(life>0){life--}`, `age=lifeStart−life`, lifeStart=32. `multiplier` (default 5) scales all thresholds. `roll` = `rand()%mod`.
  - 5 TYPES {trunk0, shootLeft1, shootRight2, dying3, dead4}. dx/dy per type (setDeltas):
    - Trunk new/dead (age≤2 || life<4): dy=0, dx=rand()%3−1 (−1..1).
    - Trunk young (age<multiplier·3): dy=−1 if age%(multiplier·0.5)==0 else 0; d10→dx: 0→−2,1-3→−1,4-5→0,6-8→+1,9→+2.
    - Trunk mid: d10 dy=−1 if dice>2 else 0; dx=rand()%3−1.
    - shootLeft: dy d10(0-1→−1,2-7→0,8-9→+1); dx d10(0-1→−2,2-5→−1,6-8→0,9→+1). shootRight mirrors dx.
    - dying: dy d10(0-1→−1,2-8→0,9→+1); dx d15(0→−3,1-2→−2,3-5→−1,6-8→0,9-11→+1,12-13→+2,14→+3) — spreads wide.
    - dead: dy d10(0-2→−1,3-6→0,7-9→+1); dx=rand()%3−1.
    - Ground clamp: `if (dy>0 && y>maxY−2) dy--`.
  - RECURSION (each loop iter, in order): life<3→recurse dead; trunk|shoot & life<multiplier+2→recurse dying; trunk & (rand()%3==0 || life%multiplier==0)→ if rand()%8==0 && life>7: new trunk life+=(rand()%5−2), shootCooldown=multiplier·2; else if shootCooldown≤0: shootLife=life+multiplier, recurse shoot alternating (shootCounter%2)+1. shootCooldown starts=multiplier, decrements each loop.
  - GLYPHS by direction (chooseString; life<4 forces dying): trunk dy0→`/~`, dx<0→`\|`, dx0→`/|\`, dx>0→`|/`; leaves = random from conf.leaves[]. Overlap guard `if (x % wcwidth(wc)==0)`.
  - COLOR: trunk/shoot bright-vs-dark wood via `rand()%2`; dying leaf bold on `rand()%10==0`; dead leaf bold on `rand()%3==0`.
  - LIVE: after each char `update_panels();doupdate()` + nanosleep(timeStep=0.03s) → visible growth. Infinite mode waits timeWait=4.0s between trees.
- BORROW: template for ANY procedural organic form (trees, lightning, rivers, cracks). Not a CellField — it's a turtle/L-system-ish stochastic walk writing glyphs into a CellGrid. The type-switch + dice-roll dx/dy + cooldown-gated branching is the reusable skeleton. New KB candidate: `procedural-branching` / `l-system-growth`.
- KB: no exact entry yet → NEW [[procedural-branching]]; links [[box-drawing-glyphs]], [[cell-grid-model]].

## 4. cmatrix — canonical matrix rain  ★ full loop
- URL: https://github.com/abishekvashok/cmatrix (verified cmatrix.c, GPLv3 — summarize only). C + ncurses.
- REAL TECHNIQUE — per-column drop state, NOT per-cell shift (new style):
  - `cmatrix{int val; bool is_head}`, grid `matrix[LINES+1][COLS]`. Parallel int arrays: length[], spaces[], updates[]. Sentinels: val −1=empty, ' '=blank, 0=white bullet, 1=`|`.
  - Only EVEN columns used (`j+=2`). Init: spaces=rand%LINES+1 (gap), length=rand%(LINES−3)+3 (stream 3..LINES−1), updates=rand%3+1 (async speed 1..3).
  - Per frame global `count` cycles 1..4; column advances only when `count>updates[j]`. Spawn: consume spaces then seed head at row0 with fresh random length + new gap. Scan down: clear old is_head, `rand()%8==0` mutates mid-stream chars (-k), write new head char + is_head at leading edge. When `y>length[j]` blank top cell + reset row0=−1 → stream detaches and scrolls.
  - DRAW: is_head (or val 0) → white, optionally bold; tail → mcolor (default green); bold for even char codes. Rainbow mode picks random color per cell.
  - CHARSET: default rand%(highnum−randmin)+randmin with default 33..123 (ASCII), console 166..217, classic half-width kana 0xff66..0xff9d.
  - TIMING: `napms(update*10)`, update default 4 → ~40ms.
- BORROW: the per-column {head,length,gap,speed} state model + async count-gating is exactly SmartCLI's matrix field; head=white/tail=green is a 1D luminance ramp down the column. Draw as CellField where each column is an independent 1D shader.
- KB: [[matrix-rain]] (exact — this is its ancestor), [[ascii-luminance-ramp]].

## 5. neo — modern truecolor matrix rain  (README-level)
- URL: https://github.com/st3w/neo (source color math not in README; behavior confirmed). C++11 + ncursesw.
- REAL TECHNIQUE (README-level): improves cmatrix with 16/256/24-bit color + wide chars.
  - Fade trail = configurable "COLOR FILE" palette interpolated head→tail ("uneven colors").
  - Auto-detect: Unicode from `$LANG` containing "UTF"; color depth from `TERM`; `--colormode` override (0=off).
  - `--glitch` (default on) randomly blinks/mutates glyphs; `--noglitch` disables. `--async` varies per-stream timing. `--charset` ascii/extended/katakana (default half-width kana), `-F` fullwidth.
  - Photosensitive-epilepsy warning (glitch flashes).
- BORROW: proves the cmatrix column model + a real truecolor head→tail gradient (via ColorModel + [[color-interpolation]]) is the modern bar. SmartCLI's version should interpolate an actual palette down the tail, not just green.
- KB: [[matrix-rain]], [[color-interpolation]], [[truecolor-24bit]], [[nearest-color-downgrade]].

## 6. no-more-secrets (nms) — Sneakers decrypt  ★ exact timing
- URL: https://github.com/bartobri/no-more-secrets (verified src/nmseffect.c). C, pure ANSI/VT100, no deps (ncurses only alt build).
- REAL TECHNIQUE — 3 phases, per-char countdown timer, probabilistic churn:
  - Constants: TYPE_EFFECT_SPEED=4ms, JUMBLE_SECONDS=2, JUMBLE_LOOP_SPEED=35ms, REVEAL_LOOP_SPEED=50ms.
  - Per char reveal timer seeded `time = rand()%5000` (0..4999ms); each reveal pass `time −= 50`. Char masked while time>0, resolves at ≤0.
  - PHASE 1 type-out: print mask chars, sleep 4ms each (wide chars get 2nd mask char).
  - PHASE 2 jumble: `(2000/35)≈57` passes, repaint all masks with fresh random chars, sleep 35ms. Between 1→2: `sleep(1)` if autoDecrypt else wait keypress (film-accurate).
  - PHASE 3 reveal: loop until all resolved; per char flip mask with prob `rand()%3==0` if <500ms left, else `rand()%10==0` (churns faster near reveal); when time≤0 print real char. sleep 50ms/pass.
  - Mask/flux chars from nmscharset (separate module); ANSI sequences (cursor hide/move/color) in nmstermio. Spaces printed as-is.
- BORROW: per-cell independent reveal timer + distance-to-resolve-driven churn probability is a clean "decrypt/materialize" CellField — each cell samples a glyph from a flux set until its timer expires, then locks the target glyph. Great for text-reveal intros. Maps directly to TTE's decrypt effect concept.
- KB: no exact entry → NEW [[decrypt-reveal]]; links [[matrix-rain]] (shared flux-glyph idea), [[cell-grid-model]].

## 7. TerminalTextEffects (tte) — effects engine  ★ real architecture
- URL: https://github.com/ChrisBuilds/terminaltexteffects (verified engine/motion.py). Python, zero deps, standard ANSI. Effects are iterators yielding frame strings; `with effect.terminal_output() as terminal: for frame in effect: terminal.print(frame)`.
- REAL TECHNIQUE — motion = distance-parametrized path traversal with easing over total distance:
  - `Waypoint(id, coord, bezier_control)` frozen/hashable; bezier_control drives the segment ENDING at it (1 ctrl pt=quadratic, 2=cubic).
  - `Path` owns waypoints + `Segment(start,end,distance)` list. Distance via `find_length_of_bezier_curve` or `find_length_of_line(double_row_diff=True)` (the `double_row_diff` = ASPECT correction! rows count double). `max_steps = round(total_distance/speed)` — speed sets distance/frame.
  - `Path.step()`: `t = current_step/max_steps` → `distance_factor = ease(t)` (easing warps time over WHOLE path, so it flows across segment boundaries) → `distance_to_travel = factor·total_distance` → walk segments subtracting distance to find active_segment → local `factor = dist_into_seg/seg.distance` → `find_coord_on_bezier_curve` or `find_coord_on_line` (lerp).
  - `Motion.move()` per frame: save previous_coord (to clear old cell), advance current_coord via step(), on end handle hold_time then loop or fire PATH_COMPLETE. `activate_path()` prepends an "origin" segment from current on-screen pos to first waypoint (stitches live position into path).
  - Events (SEGMENT_ENTERED/EXITED, PATH_COMPLETE→ACTIVATE_PATH) chain/loop paths; Path stays pure geometry, Motion holds state. Animation = separate Scene system (symbol/color frames, layers/z-order, Path-synced).
- BORROW: THE architecture reference. SmartCLI's animated widgets should adopt: (a) speed→max_steps→eased-t→coord chain, (b) easing over total path distance not per-segment, (c) `double_row_diff` = the ASPECT=2.0 rule baked into path length, (d) events to chain motion+animation, (e) iterator-yields-ANSI-frame output contract. Confirms our CellField (spatial) vs Motion (temporal path) split.
- KB: cross-cuts all — [[rendering-model]] (composition), [[terminal-cell-aspect-ratio]] (double_row_diff), [[color-interpolation]] (gradient stops/steps), [[flicker-free-rendering]] (frame emit).

## 8. cava — audio spectrum visualizer  ★ DSP core
- URL: https://github.com/karlstav/cava (verified cavacore.c). C + FFTW3. DSP split into cavacore lib.
- REAL TECHNIQUE — log-spaced bars + integral/gravity smoothing + autosens:
  - LOG FREQ bars: `freq_const = log10(low/high)/(1/(N+1)−1)`; `coeff = −freq_const + ((n+1)/(N+1))·freq_const`; `cut_off_freq[n] = high·pow(10, coeff)`. Bars <100Hz (bass_cut_off) use 2× bass FFT; rest use mid FFT. Per bar sum `hypot(re,im)` over its bin range.
  - EQ normalize: `eq[n] = (1/2^28)·pow(cut_off_freq[n+1], 0.85) / log2(FFTsize) / (bins_in_band)`. Tames huge FFT magnitudes + boosts highs.
  - GRAVITY (fall) when value dips & noise_reduction>0.1: `framerate_mod=66/framerate`; `gravity_mod=pow(framerate_mod,2.5)·2/noise_reduction`; `out = peak·(1 − fall²·gravity_mod)` clamped≥0; `fall += 0.028` each frame (accelerating fall).
  - INTEGRAL (memory) smoothing: `integral_mod=pow(framerate_mod,0.1)`; `out = mem·noise_reduction/integral_mod + out`; `mem = out`.
  - AUTOSENS: scale all by `sens`; on overshoot (>1.0, clamped) `sens·=(1−0.02·framerate_mod)`; else `sens·=(1+0.001·framerate_mod·autosens)`, faster ramp on init. Framerate estimated adaptively.
  - RENDER (separate output layer, not cavacore): Unicode eighth-blocks U+2581..U+2587 (1/8..7/8) atop full blocks U+2588 for sub-cell vertical bar resolution; ships cava.psf console font remapping.
- BORROW: eighth-block sub-cell bar rendering is exactly SmartCLI [[sub-cell-resolution]] applied vertically — a smooth progress/meter bar picks glyph by `frac*8`. The gravity+integral falloff = reusable "smooth decay toward target" for any animated meter. Log-freq + autosens are audio-specific but the smoothing generalizes.
- KB: [[sub-cell-resolution]] (eighth blocks), [[box-drawing]]; NEW candidate [[spectrum-bars]] for the DSP→bar pipeline.

## 9. pipes.sh — box-drawing pipes screensaver  ★ exact index formula
- URL: https://github.com/pipeseroni/pipes.sh (verified pipes.sh, MIT). Bash + tput + raw ANSI.
- REAL TECHNIQUE — 16-glyph table indexed by (old_dir·4 + new_dir):
  - Directions 0=up,1=right,2=down,3=left. Each pipe type = 16-char string; glyph = `str[old_dir·4 + new_dir]`. e.g. index 12 (right→down) = `┓`. 10 sets flattened; lookup `SETS[type·16 + l·4 + n]`.
    - Heavy: `"┃┏ ┓┛━┓  ┗┃┛┗ ┏━"`  Light-round: `"│╭ ╮╯─╮  ╰│╯╰ ╭─"`  Light: `"│┌ ┐┘─┐  └│┘└ ┌─"`  Double: `"║╔ ╗╝═╗  ╚║╝╚ ╔═"`  ASCII: `"|+ ++-+  +|++ +-"`
  - TURN prob: straight is `(s−1)/s` (s default 13). `n = s·RANDOM/M − 1` (M=32768); if `≥0` keep dir (straight) else `n = l + (2·(RANDOM%2)−1)` (turn ±1); `n = (n+4)%4`. Keys P/O adjust s ~4..15.
  - dir→delta: odd dirs (1,3) move x (`dx = −l+2`: dir1→+1,dir3→−1); even (0,2) move y (`dy = l−1`: dir0→−1,dir2→+1).
  - ANSI: `printf '\e[%d;%dH%s%s' row col color glyph` (1-based cursor). Color = tput setaf; wrap edges via modulo, re-randomize color/type on wrap; full reset (`tput reset`) after r chars (default 2000).
- BORROW: this is BoxJunction in miniature — but note the KEY refinement for SmartCLI: pipes.sh keys glyph on (entry_dir, exit_dir) of the SAME cell, whereas SmartCLI's [[box-drawing-glyphs]] keys on 4 edge weights. For a moving path/snake, the (in,out)→glyph table is simpler and directly reusable. The `old·4+new` index is the trick.
- KB: [[box-drawing-glyphs]] / [[box-drawing]] (BoxJunction); the (in,out) 16-table is a documented specialization.

## 10. sl — steam locomotive  (technique confirmed, low novelty)
- URL: https://github.com/mtoyoda/sl (author Toyoda Masashi). C + curses.
- REAL TECHNIQUE: big multi-line ASCII-art frames in string arrays (D51/LOGO/C51); loop decrements an x offset each tick, `mvaddstr` at shifting column, wheels alternate 2-3 frames to fake rotation, `refresh()` + small sleep. Traps SIGINT (can't Ctrl-C — the joke).
- BORROW: the sprite-scroll model — a static multi-line glyph block blitted at moving (x,y) with a small cycle of frames for sub-motion. SmartCLI = a "Sprite" over CellField (write block at offset, painter's order). Cheapest form of asciiquarium's entity.
- KB: NEW [[sprite-scroll]] (shared with asciiquarium below); [[cell-grid-model]].

## 11. asciiquarium — animated aquarium  (framework technique)
- URL: https://github.com/cmatsuoka/asciiquarium (robobunny.com/projects/asciiquarium). Perl + Term::Animation (Curses).
- REAL TECHNIQUE — scene composition on a sprite framework:
  - Sprite = multi-frame ASCII block + PARALLEL color-mask string (same shape; each letter picks a color per cell — this is the reusable trick for coloring ASCII art).
  - Integer DEPTH per entity (surface 0-9, fish 2-22, seaweed/castle 21-22) → painter's algorithm (sort by depth, draw back-to-front), NOT a pixel z-buffer.
  - Entities have callbacks for position/frame; framework does movement, collision detection (shark eats fish → callback spawns splat), off-screen cleanup. `init_random_objects()` = random spawner pool; dead entity → new random one.
  - Loop redraws continuously, polls getch(~0.5s). q/r/p keys.
- BORROW: (a) color-mask string = clean way to colorize static ASCII art (glyph layer + color layer, same dims) — adopt for SmartCLI banners/logos; (b) integer-depth painter's algorithm for multi-sprite scenes (simpler than z-buffer, right for whole-cell sprites); (c) callback-driven entity + random spawner = scene manager pattern.
- KB: NEW [[sprite-scroll]] + [[color-mask-sprites]]; [[cell-grid-model]], [[ansi-sgr-color]].

## 12. firework-rs — particle fireworks  ★ particle + gradient
- URL: https://github.com/Wayoung7/firework-rs (verified src/particle.rs + src/utils.rs). Rust + crossterm, glam Vec2.
- REAL TECHNIQUE — quadratic-drag particle sim + scalar gradient shading:
  - Particle: `pos:Vec2, vel:Vec2, trail:VecDeque<Vec2>` (records trail_length prev positions), life_state {Alive,Declining,Dying,Dead}, time_elapsed, config{init_pos,init_vel,trail_length(def 2),life_time(def 3s),color(def white)}.
  - UPDATE fixed sub-step TIME_STEP=0.001s looped to frame duration:
    - `vel += dt·(Vec2::Y·10·gravity_scale − vel.normalize()·vel.length()²·ar_scale + additional_force)`
    - `pos += dt·vel`. Quadratic air drag opposing velocity. Then trail.pop_front + push_back(pos).
  - LIFE phase from `p = elapsed/life_time`: <0.4 Alive, <0.65 Declining, <1.0 Dying, else Dead — rendering keys brightness/color fade off this ratio.
  - EXPLOSION SHAPES (utils.rs, rejection sampling — generate POSITIONS/directions): `gen_points_circle` (x²+y²≤r²), `gen_points_circle_normal` (gaussian σ=r/9, dense center), `gen_points_fan(r,n,st,ed)` (uniform, keep angle in [st,ed]), `gen_points_arc`/`gen_points_on_circle` (`(r·cos a, −r·sin a)`).
  - GRADIENT (scalar 0..1 → brightness): `explosion_gradient_1(x)=150x²` if x<0.087 else `−0.8x+1.2`; `explosion_gradient_2` piecewise ramp peaking then `−7(x−0.65)²+1.1`; `linear_gradient_1=−0.7x+1`. This scalar drives fade; RGB base from config.color.
  - Render (draw module): float pos `round()`→(isize,isize) cell; trail = VecDeque of recent positions drawn dimming.
- BORROW: reusable particle kernel — float pos/vel + gravity + quadratic drag + fixed sub-step integration, trail as a ring buffer of past positions, life-ratio→brightness gradient. SmartCLI: particles are point samples composited into a CellField; float pos → cell via round (or sub-cell via [[sub-cell-resolution]] braille for smoothness); scalar gradient × base RGB = the fade. Shape generators (circle/fan/arc via rejection sampling) seed initial velocities. Note copy-paste bug in normal-dist y bounds check (upstream).
- KB: NEW [[particle-system]]; links [[fire-lode]]/[[fire-doom-psx]] (both are particle/cellular sims), [[color-interpolation]], [[sub-cell-resolution]].

---

## Cross-cutting takeaways for SmartCLI kernel

- **CellField covers:** donut (z-buffered surface sample), lolcat (hue phase field), cmatrix/neo (per-column 1D shader), nms decrypt (per-cell timer+flux), plasma-like everything. Confirmed the S(x,y,t)→Sample model holds.
- **SubcellRaster covers:** cava eighth-blocks (vertical), firework braille smoothing. The `frac·8`→glyph pick is the shared move.
- **Motion (temporal) is a distinct axis** TTE proves out: speed→max_steps→eased-t-over-total-distance→coord, with ASPECT baked in (`double_row_diff`). SmartCLI should add a Path/Motion layer beside CellField, not fold time into the spatial shader for path-following things.
- **BoxJunction specialization:** pipes.sh (in_dir·4+out_dir)→16-glyph table is the moving-path form of the 4-edge-weight table.
- **New primitives worth adding:** Sprite (ASCII block + parallel color-mask, integer-depth painter's order — sl/asciiquarium), Particle (float pos/vel + drag + trail + life-gradient — firework-rs), ProceduralWalk (dice-roll dx/dy + cooldown-gated recursive branching — cbonsai).
- **Reveal/materialize pattern:** nms per-cell countdown + distance-driven churn probability — a text-intro effect, cousin of matrix flux.
