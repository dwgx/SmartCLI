# Animated ASCII Banner / Logo / Startup-Splash — Survey of Works

Genre: the same family as terminal /effort-style selectors and gradient logos — big ASCII/block wordmarks, gradient coloring, and frame-based terminal animation. Every entry below carries a real, verified URL. Where a page was fetchable, the ACTUAL technique (algorithm / escape sequences) was extracted, not marketing.

Date surveyed: 2026-07-08. Tools: own WebSearch + WebFetch (+ curl for raw source files).

---

## 1. GitHub Copilot CLI — "From pixels to characters" (THE richest engineering writeup)

- Engineering blog: https://github.blog/engineering/from-pixels-to-characters-the-engineering-behind-github-copilot-clis-animated-ascii-banner/
- Companion tool (open source): ASCII Motion — https://ascii-motion.app (author Cameron Foxly)
- Repo of the companion editor: https://github.com/CameronFoxly/Ascii-Motion

Reality check: despite the title, this is NOT an image→ASCII brightness-ramp pipeline. The mascot was HAND-AUTHORED frame-by-frame in a custom editor ("paint ANSI-colored ASCII like in Photoshop, one character at a time"). ~6,000 lines of TypeScript in production.

Actual techniques:
- Block-art glyphs: `█ ▄ ▀ ▐ ▌ ┌ ┐ └ ┘ │ ─`.
- SEMANTIC COLOR ROLES, not literal hues. Deliberately a minimal **4-bit ANSI palette** (not truecolor/256) so terminals/themes can override:
  ```ts
  type AnimationElements =
    | "block_text" | "block_shadow" | "border"
    | "eyes" | "head" | "goggles"
    | "shine" | "stars" | "text";
  ```
  Dark theme: cyan block_text, greenBright eyes, magentaBright head, cyanBright goggles, yellowBright stars. Light theme swaps to blue/green/magenta/cyan/yellow. Rationale: terminals remap colors by theme/OS/high-contrast/bg, so "you can't rely on exact hues." Wordmark treated as a graphical object, not body text (different WCAG contrast handling).
- Raw escapes in the prototype: `\x1b[35m` magenta, `\x1b[36m` cyan, `\x1b[37m` white, reset `\x1b[0m` after each char.
- Frame format: plain-text `content` + a `"row,col" -> role` map:
  ```ts
  interface AnimationFrame {
    title: string;
    duration: number;   // per-frame ms, e.g. 80
    content: string;
    colors?: Record<string, AnimationElements>; // "3,1": "head"
  }
  ```
  ~20 frames, 11×78 area, ~10 elements/frame, ~3s total.
- Render step: truncate each line to 80 chars, resolve every char's color, then **run-length group consecutive same-color chars into segments** to minimize escape output (the closest thing to "diffing"; no per-frame delta diff).
- Cursor control (prototype only): `readline.cursorTo(stdout,0,0)` + `readline.clearScreenDown(stdout)` then `setInterval(render,75)` (~13fps = flicker ceiling on some terminals). Production runs on **Ink** (React for terminal) via `<Text color={...}>` + `useState`/`setInterval`. Ink re-renders on every state change; it is NOT an animation engine (no frame deltas, no paint-cycle sync).
- Compatibility: keep animation < 3s (never blocks interaction), separate static from animated components to cut redraws, treat as best-effort. Tested iTerm2, Windows Terminal, VS Code + dozens of theme combos. Accounts for terminals that throttle fast writes / reveal cleared frames / buffer differently.
- Accessibility: opt-in behind a flag (not shown by default after first use); `--screen-reader` mode skips the banner entirely; respects system color overrides; minimizes ANSI that confuses assistive tech.

Secondary coverage (not primary): https://app.daily.dev/posts/from-pixels-to-characters-the-engineering-behind-github-copilot-cli-s-animated-ascii-banner-by6szkb17 ; mirror https://noise.getoto.net/2026/01/28/from-pixels-to-characters-the-engineering-behind-github-copilot-clis-animated-ascii-banner/

---

## 2. oh-my-logo (shinshin86) — Claude/Gemini-style gradient banners

- Repo: https://github.com/shinshin86/oh-my-logo
- Show HN: https://news.ycombinator.com/item?id=44395596
- Web version (SVG/PNG export): https://github.com/pucodev/omlg

Actual techniques:
- Two render modes:
  1. **Outlined (default):** text → `figlet` (default font `Standard`, selectable via `-f`/`--font`/`OHMYLOGO_FONT`) → apply a `gradient-string` gradient across the ASCII art. Direction `vertical` | `horizontal` | `diagonal`; `--reverse-gradient` flips stop order.
  2. **Filled block mode:** block glyphs rendered via **Ink** (`renderFilled` → stdout), block fonts = `3d, block(default), chrome, console, grid, huge, pallet, shade, simple, simple3d, simpleBlock, slick, tiny` (these control shadow style), `letterSpacing` option, default horizontal gradient, cleanup timeout `OHMYLOGO_RENDER_TIMEOUT_MS` (default 250ms).
- Palettes are plain hex-stop arrays in `src/palettes.ts` (`PALETTES` object). 13 built-in: `grad-blue`(default), sunset, dawn, nebula, ocean, fire, forest, gold, purple, mint, coral, matrix, mono. e.g. sunset = `#ff9966 → #ff5e62 → #ffa34e`. Custom via `--palette-colors` (JSON or CSV).
- Deps: figlet + gradient-string + ink. TTY detection with `--color`/`--no-color`. License MIT AND CC0-1.0 (generated logos are CC0).
- API: `render`, `renderFilled`, `PALETTES`, `resolvePalette`, `getPaletteNames`, `getDefaultPalette`, `getPalettePreview`.

---

## 3. gradient-string (bokub) — the gradient engine used everywhere

- Repo: https://github.com/bokub/gradient-string
- npm: https://www.npmjs.com/package/gradient-string

Actual techniques:
- Takes an array of colors + a string; maps each char position to a point [0..1] along the gradient, computes its color, wraps it in a terminal escape.
- Stops distributed equidistantly by default; override with `{color, pos}` objects (pos 0..1).
- `multiline()`: measures the longest line and computes gradient positions against that shared width, so every COLUMN gets a consistent color across all rows → vertically aligned gradients for ASCII art.
- Color interpolation: parse via **TinyColor** (hex/rgb/hsva/CSS/named), gradient via **tinygradient**. `interpolation: 'rgb'(default) | 'hsv'` ("HSV usually produces brighter colors"). `hsvSpin: 'short'(default) | 'long'` picks direction around the hue circle.
- Terminal output via **chalk** (exact 24-bit emission is in src/, not README).
- Deps: chalk, tinygradient, TinyColor. 100% TypeScript.

---

## 4. chalk-animation (bokub) — frame-based animated text effects

- Repo: https://github.com/bokub/chalk-animation

Actual techniques (API-level; impl is in index.js):
- Six effects: **rainbow, pulse, glitch, radar, neon, karaoke**. `chalkAnimation.rainbow('...')`.
- Auto-starts on creation; `stop()`/`start()` pause/resume; `render()` manual frame; `frame()` returns next frame content → each effect is a discrete frame sequence advanced on a timer.
- Speed is a multiplier (default 1, >0) scaling frame interval (not fixed fps). `replace()` swaps text seamlessly; any console print stops the animation (it overwrites the current line until interrupted).
- CLI: `--duration` (default Infinity), `--speed`. MIT.
- NOTE: to get the exact color-cycling math + line-redraw escapes, read index.js directly (flagged for deep-dive).

---

## 5. cfonts (dominikwilkowski) — block-font banners with gradients

- Repo: https://github.com/dominikwilkowski/cfonts
- npm: https://www.npmjs.com/package/cfonts
- Python port: https://github.com/frostming/python-cfonts

Actual techniques (README-level; internals in rust/ + nodejs/):
- Fonts: block, simpleBlock, simple, 3d, simple3d, chrome, huge, shade, slick, grid, pallet, tiny, console. (Font data = character grids; exact JSON/buffer structure lives in source.)
- Gradient modes:
  - Normal (2 colors): interpolates through "as many colors as it can find" left-to-right for a rich spread.
  - **Transition (`-t`):** supply >2 colors, each transitioned to directly (you control the stops).
  - **Independent (`-i`):** recompute gradient PER LINE instead of across the whole banner.
- Color support auto-detected; override `FORCE_COLOR` (e.g. `=3` truecolor, overrides `NO_COLOR`), disable via `NO_COLOR`. chalk-based output.
- Repo is ~56% Rust, ~24% JS. (Read rust/ + nodejs/ for the interpolation granularity — per-column vs per-char not documented.)

---

## 6. figlet / FIGfont standard — the foundational big-letter renderer

- Man page: http://www.figlet.org/figlet-man.html
- FIGfont v2 spec (primary): http://jave.de/figlet/figfont.html and http://roysac.com/learn/figfont-standard.html
- Spec text (raw): https://github.com/lukesampson/figlet/blob/master/figfont.txt
- What-is/history: https://ezascii.com/blog/what-is-figlet-and-what-can-you-do-with-it

Actual algorithm:
- Each input char → a multi-line FIGcharacter of "sub-characters"; stitched horizontally (also RTL). `.flf` files.
- **Header line:** `flf2a$ 6 5 20 15 3 0 143 229` =
  signature+hardblank (`flf2a` + hardblank char, conventionally `$`), Height, Baseline, Max_Length, Old_Layout(-1..63), Comment_Lines, Print_Direction(0=LTR,1=RTL), Full_Layout(0..32767), Codetag_Count. First 7 required, last 3 optional.
- **Hardblank (`$`):** renders as a space, but treated as a visible sub-char while fitting/smushing (prevents over-smushing e.g. C→G).
- **Endmark:** usually `@`/`#`; driver strips the last block of consecutive equal chars per line (last line has two endmarks, others one).
- **Spacing modes:** full-width (`-W`), kerning (`-k`, remove blanks until touching, no smush), smushing (`-s`/`-S`, remove overlapping sub-chars), overlap (`-o`).
- **6 horizontal smushing rules (Full_Layout bits):** 1 Equal(1), 2 Underscore(2), 3 Hierarchy(4), 4 Opposite Pair(8), 5 Big X(16), 6 Hardblank(32).
  - Rule 2: `_` replaced by any of `| / \ [ ] { } ( ) < >`.
  - Rule 3 hierarchy classes: `|`, `/\`, `[]`, `{}`, `()`, `<>`.
  - Rule 5: `/\`→`|`, `\/`→`Y`, `><`→`X`.
- **5 vertical smushing rules:** 1 Equal(256), 2 Underscore(512), 3 Hierarchy(1024), 4 Horizontal Line(2048), 5 Vertical Line Supersmushing(4096).
- **Layout bitmask:** 64 = kerning by default, 128 = h-smush by default (overrides 64), 8192 = vertical fitting, 16384 = vertical smushing (overrides 8192). No rules set for an axis ⇒ universal smushing. Old_Layout -1 = full-width, 0 = kerning.
- Related: pyfiglet (Python port), toilet (TOIlet, adds color + `.tlf` fonts + Unicode), JS port https://github.com/lukesampson/figlet.

---

## 7. lolcat (tehmaze, Python port) — sine-wave rainbow, EXACT algorithm extracted

- Repo: https://github.com/tehmaze/lolcat
- Original Ruby: busyloop/lolcat. Go tutorial (clear reimpl): https://flaviocopes.com/go-tutorial-lolcat/

Actual algorithm (pulled from raw source file `lolcat`):
- **Rainbow function** — 3 sine waves 120° (2π/3) out of phase:
  ```py
  def rainbow(self, freq, i):
      r = math.sin(freq * i) * 127 + 128
      g = math.sin(freq * i + 2*math.pi/3) * 127 + 128
      b = math.sin(freq * i + 4*math.pi/3) * 127 + 128
      return [r, g, b]
  ```
- **Position feed:** per char, `rgb = rainbow(options.freq, options.os + i / options.spread)` where `i` = column index, `options.os` = offset (random seed `random.randint(0,256)` unless `--seed`), incremented by 1 per LINE (`options.os += 1`) so the rainbow shifts diagonally down. `spread` stretches the wave horizontally.
- **Color emission:** 256-mode builds a color cube index: `sum([16] + [int(6*val/256)*mod for val,mod in zip(rgb,[36,6,1])])` → escape `'38;5;%d'`. 8/16-mode nearest-matches an ANSI palette by squared RGB distance. `wrap(*codes)` → `'\x1b[%sm'`.
- **Animation mode:** hide cursor `\x1b[?25l` at start, show `\x1b[?25h` at end. Per line, loop `duration` times: cursor-left `\x1b[%dD` (len of line) to return to line start, bump `options.os += options.spread`, reprint, `time.sleep(1.0/speed)`. That phase bump per frame = the shimmering scroll.
- Mode detection: ANSICON→16, ConEmuANSI=ON→256, `-256color`/xterm/screen→256, `-color`/rxvt→16, else 256.

---

## 8. Ink + ink-gradient + ink-big-text — the React-for-terminal splash stack

- Ink: https://github.com/vadimdemedes/ink (readme raw: https://raw.githubusercontent.com/vadimdemedes/ink/refs/heads/master/readme.md)
- ink-gradient: https://github.com/vadimdemedes/ink-gradient (npm https://www.npmjs.com/package/ink-gradient)
- ink-big-text: https://github.com/sindresorhus/ink-big-text (npm https://www.npmjs.com/package/ink-big-text)

Actual techniques:
- Ink = React component model → renders JSX to stdout via Yoga flexbox layout; re-renders on state change (used by Copilot CLI, Gemini CLI which upgraded to Ink 6 + React 19: https://github.com/google-gemini/gemini-cli).
- ink-big-text = wraps **cfonts** as a component (`<BigText text=.../>`, `font`, `colors`, `backgroundColor`, `letterSpacing`, `space`).
- ink-gradient = wraps **gradient-string** as a component (`<Gradient name="rainbow"><BigText.../></Gradient>`); composes with ink-big-text to make the classic gradient block splash. Accepts a string or Ink component as children.
- Animation = drive component state with setInterval/useEffect (same pattern Copilot CLI production uses).

---

## 9. gradient-figlet (peterfritz) — one-shot gradient FIGlet CLI

- Repo: https://github.com/peterfritz/gradient-figlet

Straightforward composition: FIGlet ASCII art + gradient-string, exposed as a single `npx` command. Good minimal reference for the figlet→gradient pipeline (thinner writeup; use as a code sample, not a design doc).

---

## 10. Image → ASCII (brightness-ramp) — the "pixels to characters" technique done for real

- Blog (browser + terminal): https://blog.openreplay.com/ascii-art-browser-terminal/
- Character-set tutorial: https://ezascii.com/tutorials/choosing-the-best-character-set-for-your-project
- Rust impl w/ edge detection: https://lib.rs/crates/ascii-typographer
- Luminance formula ref: https://agentcalc.com/image-to-ascii-converter

Actual algorithm:
- Pipeline: sample image → grid of cells → average brightness/cell → map to a char → output with optional color.
- **Luminance:** `Y = 0.2126*R + 0.7152*G + 0.0722*B` (Rec.709 perceptual weights).
- **Character ramp:** `' .:-=+*#%@'` (10 steps). Map:
  ```js
  const palette = ' .:-=+*#%@';
  const index = Math.floor((brightness/255) * (palette.length-1));
  return palette[index];
  ```
  (Reverse the ramp if dark bg — with space at index 0, low brightness→space, high→`@`.) A denser 70-char ramp `"$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^\`'. "` is common for finer gradation.
- **Sampling (browser):** draw to offscreen canvas, read `ctx.getImageData()`, one char per cell into a `<pre>` or `fillText()`. Compensate for char aspect ratio (~2:1 tall) by sampling wider cells.
- **Color (ANSI truecolor):** `\033[38;2;R;G;Bm` foreground, reset `\033[0m`. Example `printf '\033[38;2;255;100;0m%s\033[0m\n' "orange"`.

---

## Other references seen (lower priority)

- khrome/ascii-art (Node, image+text+fonts, compositing): https://github.com/khrome/ascii-art/blob/master/README.md
- AlexLakatos/ascii-themes (themed ASCII generator CLI): https://github.com/AlexLakatos/ascii-themes
- oharu121/cli-ascii-logo: https://github.com/oharu121/cli-ascii-logo
- chalk (base terminal styling / color-level detection): referenced by nearly all of the above.

---

## Cross-checks / corrections made
- Copilot CLI blog title "pixels to characters" is a metaphor — art is hand-authored, NO image pipeline. Do not cite it as a brightness-ramp source (use entry #10 for that).
- oh-my-logo "Zero Dependencies" claim = zero-install via npx, NOT zero bundled libs (it bundles figlet/gradient-string/ink).
- The openreplay blog's prose ("dense=dark") contradicts its own code (index 0 = space = darkest input); ramp direction depends on whether your value means brightness or darkness.
