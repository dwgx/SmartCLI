# Terminal Visual-Art / Animation Projects — Raw Findings

Survey date: 2026-07-08. Sources verified via WebSearch + WebFetch of primary repos/blogs.
Every entry carries a real URL. Techniques extracted from source/README/author writeups where fetchable.
Where a technique claim could only be confirmed from a README (not source), it is marked "(README only)".

---

## 1. cmatrix — Matrix digital rain (the canonical one)
- Repo: https://github.com/abishekvashok/cmatrix
- Shows: green "digital rain" of falling characters, The Matrix style. Supports color options, async scroll, screensaver mode, rainbow, bold.
- Technique: C + **ncurses**. Each column tracks a falling "drop"; per frame it shifts characters down one row, randomizes the leading char, and dims the trail. Classic approach: array per column of `{char, is_head}`; head drawn bright/white, tail in green, oldest cleared. Uses ncurses `mvaddch`/color pairs, not raw ANSI.
- Note: the ancestor that nearly every other matrix-rain clone cites as "based on cmatrix."

## 2. unimatrix — Python matrix rain, unicode/katakana
- Repo: https://github.com/will8211/unimatrix (active fork: https://github.com/chrisfrazier0/unimatrix)
- Shows: Matrix rain using **half-width katakana** unicode by default; custom character sets; live keyboard controls (speed, color, async).
- Technique: Python + curses. "Based on CMatrix" per its own description. Column-drop model like cmatrix but with configurable `-c` color, `-s` speed, `-l` character-set flags (letters, digits, katakana, custom). Pure-python, uses `curses`.

## 3. neo — modern matrix rain, true color
- Repo: https://github.com/st3w/neo
- Shows: Matrix rain with 16/256/**32-bit (24-bit + alpha) true color**, katakana default, glitch/blink effect, message display, resizing.
- Technique (README): C++11 + **ncursesw** (wide chars). Auto-detects terminal color depth and Unicode support from `$LANG`. Fading trail achieved via "uneven colors" palette + configurable COLOR FILE. `--glitch` randomly blinks glyphs; `--async` varies per-stream timing; `--charset` picks ascii/extended/katakana. Explicit photosensitive-epilepsy warning. Improves on cmatrix with real truecolor gradients + Unicode.

## 4. cbonsai — procedural bonsai tree generator  ★ rich technique extracted
- Repo: https://gitlab.com/wellons/cbonsai (author: Chris Wellons / "John Allen")
- Shows: procedurally-grown ASCII bonsai, unique each run (seedable), live "grow" animation, potted with base art.
- Technique (from cbonsai.c source): C + **ncurses + panel library**.
  - Core is recursive `branch(conf, y, x, type, life)`; loops `while(life>0)`, `life--` each step, `age = lifeStart - life`.
  - **5 branch types** via switch: 0 trunk, 1 shoot-left, 2 shoot-right, 3 dying, 4 dead.
  - Movement `(dx,dy)` chosen by `roll(&dice, mod)` = `rand()%mod`, plus `rand()%3 - 1`. Trunk behavior depends on age (young=grow wide+up, mid=up, old/dead=flat jitter). Dying spreads horizontal (dx -3..3 on mod 15). Dead fills leaves.
  - Ground clamp: `if (dy>0 && y>(maxY-2)) dy--;`
  - **Recursion/branching**: `life<3` → recurse dead(4) leaves; `life < multiplier+2` → recurse dying(3); living trunk may spawn new trunk (life perturbed `rand()%5-2`) or, after `shootCooldown` expires, a shoot (`shootLife = life+multiplier`, alternating L/R via `shootCounter%2+1`). shootCooldown starts `multiplier`, resets to `multiplier*2`.
  - **Glyphs** by direction: flat trunk `/~`, centered `/|\`; leaves random from `conf.leaves[]`. Colors via `wattron`/`COLOR_PAIR`, random bold for texture.
  - **Pot/base**: `drawWins()` picks base size by baseType (1 = 31×4, 2 = 15×3), centers on screen, draws rim/soil/body in different color pairs; leaves-in-pot literal `./~~~\.`.
  - **Live mode**: after each char, `update_panels(); doupdate();` + `nanosleep(timeStep)` (default 0.03s split into sec/nsec) → step-by-step growth.
  - ncurses setup: `initscr, noecho, curs_set(0), cbreak, nodelay(TRUE)`; `use_default_colors()` for -1 bg; 16 color pairs; panels stack baseWin/treeWin.
  - Tree planted with single `branch(conf, maxY-1, maxX/2, 0, lifeStart)` (default life 32).

## 5. pipes.sh — animated pipes screensaver
- Repo: https://github.com/pipeseroni/pipes.sh
- README: https://github.com/pipeseroni/pipes.sh/blob/master/README.rst
- Shows: box-drawing "pipes" that snake around the terminal, turning at random, leaving colored trails; wipes and restarts when screen fills.
- Technique (README): Bash 4+ + `tput` (ncurses terminfo), 24-bit color needs tput >= 6.1.
  - Each pipe "type" = a **16-character string of box-drawing glyphs** (e.g. type 0 = `┃┏ ┓┛━┓ ┗┃┛┗ ┏━`). The 16 positions map (current direction × next direction) → correct straight/corner glyph. Custom pipes via `-t cXXXXXXXXXXXXXXXX` (e.g. `cMAYFORCEBWITHYOU`).
  - Turning is **probabilistic** — `P`/`O` keys adjust "probability of straight pipes"; RNG picks turn vs straight each step, biased by that chance.
  - Cursor movement via `tput cup` / ANSI positioning; color via `tput setaf`. Resets/clears when the screen fills. (Exact source RNG not read; README-level.)

## 6. asciiquarium — animated ASCII aquarium
- Repo: https://github.com/cmatsuoka/asciiquarium (author page: https://robobunny.com/projects/asciiquarium/)
- Shows: fish, sharks, whales, ships, castle, seaweed, bubbles, sea monster — full animated sea scene.
- Technique: single **Perl** script on **Term::Animation** framework (uses `Curses`, `Term::Animation::Entity`).
  - Sprites = multi-frame ASCII-art blocks + parallel **color-mask strings** (same shape, letters pick colors per cell).
  - **Depth/z-layering** via `%depth` hash (surface 0-9, fish/sharks 2-22, seaweed/castle 21-22) — painter's-algorithm ordering, not a pixel z-buffer.
  - Entities have **callback routines** controlling position/frame; framework handles movement, **collision detection** (shark eats fish → callback spawns splat), and cleanup off-screen.
  - `init_random_objects()` = randomized spawner pool; when an entity dies/exits, a new random one is chosen.
  - Main loop redraws continuously, polls curses `getch()` (~0.5s delay). `q` quit, `r` redraw, `p` pause, `-c` classic mode.

## 7. sl — Steam Locomotive
- Repo: https://github.com/mtoyoda/sl (author Toyoda Masashi)
- Shows: an ASCII steam train chugs left-to-right across the screen when you mistype `sl` for `ls`. Options: `-a` (accident/people crying for help), `-l` (little), `-F` (flying), `-c` (C51 loco).
- Technique: C + **curses**. Big multi-line ASCII-art train stored as string arrays (LOGO/D51 frames); animation loop decrements an x offset each tick, `mvaddstr`s the loco frames at shifting column, wheels alternate between 2-3 frames to fake rotation, `refresh()` + small sleep. Ignores SIGINT so you can't Ctrl-C out — part of the joke.

## 8. lolcat — rainbow text colorizer  ★ exact algorithm extracted
- Repo: https://github.com/busyloop/lolcat
- Shows: pipes any stdin text and paints it in a smooth animated rainbow gradient (diagonal across lines).
- Technique (from lib/lolcat/lol.rb): **Ruby**, colors via the `Paint` gem.
  - Core `rainbow(freq, i)`:
    - `red   = sin(freq*i + 0)        * 127 + 128`
    - `green = sin(freq*i + 2π/3)     * 127 + 128`
    - `blue  = sin(freq*i + 4π/3)     * 127 + 128`
    - → 3 sine waves phase-offset 120°/240° around the color wheel; `*127+128` maps [-1,1]→[1,255]. Returns `#RRGGBB`.
  - Position per char: `color = rainbow(opts[:freq], @os + i/opts[:spread])`. `freq` = hue cycle speed, `spread` = how many chars per hue step (stretch), `@os` = offset/seed (starts at `opts[:os]`, +1 per line → diagonal gradient; animate mode increments over time).
  - Output: `Paint.color(color)` emits `38;2;r;g;b` (truecolor when `COLORTERM=truecolor/24bit` or `--truecolor`), else downsamples to nearest 256-palette `38;5;n`. Resets with `\e[39m` (or `\e[49m` inverted bg).
- Note: the sine-wave RGB trick is *the* reference implementation copied by dozens of clones (Go, Rust lolcrab, C clolcat).

## 9. no-more-secrets (nms) — Sneakers (1992) decrypt effect
- Repo: https://github.com/bartobri/no-more-secrets (author Brian Barto; libNMS extracted for reuse)
- Shows: reads stdin, first displays it as random noise, then animates a character-by-character "decryption" back to the real text — the famous 1992 *Sneakers* movie effect. Companion `sneakers` mode mimics the film screen.
- Technique: **C**, default build **no deps — pure ANSI/VT100 escape sequences** (so it works inline without clearing the screen). Alternate **ncurses** build for non-VT100 terminals (always clears screen).
  - Each character gets a random "reveal time" + churns through random **flux/feedback characters** at intervals before settling on the true glyph.
  - Waits for a keypress before starting decryption (film-accurate); `-a` auto-starts; `-s` masks single spaces; `-f <color>` sets reveal color (blue default); `-c` saves/clears/restores terminal state. (No real cryptography — purely visual scramble→unscramble.)

## 10. cava — console audio spectrum visualizer
- Repo: https://github.com/karlstav/cava
- Shows: real-time bar-spectrum audio visualizer in the terminal (also SDL/desktop). Bars react to music frequency bands.
- Technique: **C**, uses **FFTW3** for the FFT. Core DSP split into a separate `cavacore` lib (see CAVACORE.md).
  - Renders bars using **Unicode eighth-blocks U+2581–U+2587** (1/8..7/8) on top of full blocks for sub-cell vertical resolution. Ships `cava.psf` console font remapping chars 1-7 to those blocks for TTY use.
  - Input backends via `method=`: **PipeWire (default), PulseAudio, ALSA** (needs `snd_aloop` loopback), plus MPD/fifo, JACK, sndio, OSS, shmem, CoreAudio, Windows.
  - Config `[eq]` per-band scaling; runtime sensitivity via arrow keys; ncursesw optional alt output. (monstercat smoothing / gravity / autosens live in cavacore.c — not read here.)

## 11. TerminalTextEffects (tte) — modern effects engine  ★ rich architecture
- Repo: https://github.com/ChrisBuilds/terminaltexteffects
- Docs: https://chrisbuilds.github.io/terminaltexteffects/  |  PyPI: https://pypi.org/project/terminaltexteffects/
- Shows: a whole library of polished text-reveal effects — beams, blackhole, burn, decrypt, fireworks, matrix, rain, pour, slide, spotlights, swarm, vhstape, waves, wipe, ~40 total.
- Technique (README/docs): **Python, zero 3rd-party deps, standard ANSI sequences**. Engine primitives:
  - **Canvas** = render surface (matches terminal / text extents / fixed); cardinal+diagonal anchor points.
  - **Motion**: characters move along **Paths** built from **Waypoints** with **easing** functions and **bezier curves**.
  - **Animation**: **Scenes** drive symbol/color changes, **layers** (z-order), easing, and Path-synced progression.
  - **Gradients**: variable stop/step multi-color gradient generation. Color: Xterm-256 / RGB hex.
  - **Event system**: callbacks fire on Path/Scene state changes.
  - **Iterator/frame model**: `effect = Rain(text); for frame in effect: ...` — each iteration yields a frame string. `terminal_output()` context manager handles setup/teardown/cursor/frame-rate (default 60fps, configurable, 0=unlimited).
  - Parses fetch-style input: SGR fg/bg colors, cursor CSI moves, CR, some DEC private modes (not a full emulator; fails fast on unsupported sequences).
  - Each effect has a typed config dataclass auto-exposed as CLI args. Custom effects drop-in as `.py` with `get_effect_resources()`.
- Note: the current gold-standard for "how to architect a terminal effects engine" — most relevant reference for a fresh implementation.

## 12. donut.c — spinning ASCII torus  ★ exact math extracted
- Author blog (primary): https://www.a1k0n.net/2011/07/20/donut-math.html  (optimization follow-up: https://www.a1k0n.net/2021/01/13/optimizing-donut.html)
- Andy Sloane's famous obfuscated C that renders a rotating, lit 3D donut in ASCII.
- Technique (from a1k0n's writeup): C, raw `printf` + cursor-home escape.
  - **Torus param**: circle radius R1=1 centered at (R2=2,0,0), swept by θ, then revolved around y-axis by φ.
  - **Rotations**: extra spin = rotation A about x-axis + B about z-axis. Final point:
    - `x = cx·(cosB·cosφ + sinA·sinB·sinφ) − cy·cosA·sinB`
    - `y = cx·(sinB·cosφ − sinA·cosB·sinφ) + cy·cosA·cosB`
    - `z = K2 + cosA·cx·sinφ + cy·sinA`   where `cx=R2+R1cosθ, cy=R1sinθ`.
  - **Perspective**: `ooz = 1/z`; `xp = W/2 + K1·ooz·x`, `yp = H/2 − K1·ooz·y` (y negated for screen). K2=5, K1 from screen size.
  - **Z-buffer** stores **1/z** (init 0 = infinitely far); draw only if `ooz > zbuffer[xp][yp]`.
  - **Luminance** = surface-normal · light dir (0,1,−1):
    `L = cosφcosθsinB − cosAcosθsinφ − sinAsinθ + cosB(cosAsinθ − cosθsinAsinφ)` (range −√2..+√2). If L≤0 skip.
    - `char = ".,-~:;=!*#$@"[ (int)(L*8) ]` — 12-char ramp dim→bright (8·√2 ≈ 11.3).
  - No raytracing: just densely plot torus surface points at fixed θ/φ steps.

---

## Additional notable works (secondary, real URLs)

- **hollywood** — https://github.com/dustinkirkland/hollywood — bash script that splits a byobu/tmux console into random panes each running a fake "busy hacker" activity (hexdump, network traffic, ccze log color, watch, htop-like). Rearranges splits every N sec (`-s` splits, `-d` delay). Pure orchestration of existing CLI tools inside tmux panes.
- **firework-rs** — https://github.com/Wayoung7/firework-rs — cross-platform ASCII firework **particle system** in Rust, backend **crossterm**. `-g` color gradient trails (truecolor; wants black bg + GPU terminal). Configurable shapes (fountain, vortex, heart). (Physics fields in src/, not read.)
- **addyosmani/firew0rks** — https://github.com/addyosmani/firew0rks — Node terminal fireworks / text-art animation player.
- **PyBonsai** — https://github.com/Ben-Edwards44/PyBonsai — pure-Python procedural ASCII trees (cbonsai-inspired, angle/branch recursion).
- **coq-bonsai** — https://github.com/formal-land/coq-bonsai — bonsai generator written in Coq (novelty/formal-methods angle).
- **pymatrix-rain** — https://github.com/tech-chad/pymatrix-rain — Python 3 + curses matrix rain, many color/effect flags.
- **bradfitz/sneakers-effect** — https://github.com/bradfitz/sneakers-effect — JS homage to the Sneakers decrypt effect (web).
- **djdarcy/spinning-donut** — https://github.com/djdarcy/spinning-donut — annotated/educational donut reimplementation.

## Cross-cutting technique patterns observed
- **Two rendering families**: (a) **ncurses/curses** (cmatrix, cbonsai, sl, asciiquarium via Term::Animation, neo/ncursesw) — screen buffer + color pairs, usually clears screen; (b) **raw ANSI/VT100 escapes** (nms default, lolcat, donut, tte, pipes via tput) — can render inline, more portable.
- **Sub-cell resolution**: cava uses U+2581–2587 eighth-blocks; general trick for smooth bars.
- **Color**: modern tools emit `\e[38;2;r;g;b` truecolor (lolcat, neo, tte, firework-rs), older/portable ones use 16/256 (`\e[38;5;n`) or ncurses COLOR_PAIRs.
- **Depth**: donut uses a real 1/z z-buffer; asciiquarium uses integer depth + painter's algorithm.
- **Animation loop**: fixed timestep (`nanosleep`/frame-rate cap ~30-60fps) + non-blocking key poll (`nodelay`/`getch`) is universal.
- **Procedural generation**: cbonsai's recursive-branch-with-dice-rolls is the template for organic ASCII growth.
