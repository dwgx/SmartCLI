# Works — learning from other people's real works

Each entry studies one real, shipped project: what it is, the **Source:** URL, the actual technique extracted from its source (not head-canon), what SmartCLI's engine can concretely borrow, and `[[links]]` to the KB principles/effects it demonstrates.

Grounded only in the deep-dive digests in `../sources/` (`deep-art.md`, `deep-tui.md`, `deep-banner.md`), which in turn distill the raw project surveys (`../sources/works-art.md` for the visual-art works, `../sources/works-tui.md`, `../sources/works-banner.md`, `../sources/works-galleries.md`). Anything not confirmed to source line is marked *(verify)*.

## Visual art — effects & procedural forms
- [[donut-c]] — spinning shaded ASCII torus: parametric surface + `ooz` projection + z-buffer + `L*8` ramp.
- [[lolcat]] — sine-wave rainbow: three offset sines → RGB, diagonal phase per line.
- [[cbonsai]] — procedural bonsai: recursive branching with per-type direction dice + cooldown-gated shoots.
- [[cmatrix]] — reference matrix rain: per-column `{head,len,gap,speed}`, white head / green tail.
- [[neo]] — truecolor matrix rain: interpolated head→tail palette, `$LANG`/`$TERM` autodetect.
- [[no-more-secrets]] — "decrypt" reveal: per-cell countdown + distance-driven churn, lock at zero.
- [[terminaltexteffects]] — motion architecture: `speed → max_steps → eased t → coord`, effects as ANSI-yielding iterators.
- [[cava]] — audio spectrum bars: log-spaced bins, gravity fall + integral smoothing, eighth-block sub-cell.
- [[pipes-sh]] — moving pipes: `(in_dir,out_dir) → 16-glyph` corner table, `(s-1)/s` turn probability.
- [[sl]] — steam-locomotive sprite scroll: static glyph block blitted at moving `(x,y)` with a small frame cycle.
- [[asciiquarium]] — animated aquarium: parallel color-mask sprites + integer-depth painter's order + spawner.
- [[firework-rs]] — particle fireworks: float pos/vel, gravity + quadratic drag, fixed sub-step, trail ring buffer.

## TUI frameworks — layout, rendering, color, responsiveness
- [[textual]] — CSS box model + grid + `fr`; Segment compositor + spatial-map; DOM-bubbling key bindings.
- [[ratatui]] — Cassowary constraint layout; double-buffer Cell-diff render loop.
- [[bubbletea-lipgloss]] — single-consumer Elm loop + DEC-2026 sync output; Lip Gloss Join/Place + value-type styles.
- [[termenv]] — exact truecolor→256→16 degrade with HSLuv (perceptual) distance.
- [[notcurses]] — sub-cell blitter geometry (2x1/2x2/3x2/4x2/braille/pixel) + the "2 colors per cell" rule.
- [[chafa]] — 8×8 coverage-bitmap symbol matching for high-fidelity image→Unicode.
- [[fzf]] — FuzzyMatchV2 (Smith-Waterman) scoring constants for command palettes.
- [[yazi]] — async-off-render-thread + discardable-ticket model for responsive previews/highlighting.

## Banners & logos — big text, gradients, animated splashes
- [[copilot-cli-banner]] — hand-authored frames + `"row,col"→semantic-role` 4-bit color map + run-length segments; accessibility/duration gating.
- [[gradient-string]] — per-char gradient; multiline mode consumes color per char (incl spaces) for vertical alignment.
- [[chalk-animation]] — in-place redraw `\x1b[nF\x1b[G\x1b[2K` + exact per-effect frame math (rainbow/pulse/glitch/radar/neon/karaoke).
- [[cfonts]] — `<cN>`-tagged fixed-height glyph-grid block fonts (body vs shadow).
- [[figlet]] — FIGfont v2 spec: hardblank, endmark, 6+5 smushing rules, layout bitmask.
- [[image-ascii-ramp]] — the real pixels→chars: Rec.709 luminance → `' .:-=+*#%@'` ramp + optional truecolor.
- [[ink-splash-stack]] — oh-my-logo & Ink composable splashes: shape (FIGlet/block) + color (gradient) as two stages.

## Galleries
No gallery works were part of this digest set. Raw gallery notes live in `../sources/works-galleries.md` *(verify — not distilled into entries here)*.

---

## How these map to the graph
The works wing is the "applied" layer: every entry points *down* into the concept graph. High-traffic targets:
- **Rendering:** [[rendering-model]], [[flicker-free-rendering]], [[cell-grid-model]], [[sub-cell-resolution]]
- **Effects:** [[matrix-rain]], [[ascii-luminance-ramp]], plus the composed-form concepts these works motivated (now authored — see below)
- **Color:** [[color-interpolation]], [[nearest-color-downgrade]], [[256-color-cube]], [[truecolor-24bit]], [[hsv-cycling-lolcat]]
- **Layout:** [[box-model-on-cell-grid]], [[fractional-space-distribution]]
- **Image:** [[image-to-ansi-halfblock]]
- **TUI patterns:** [[fuzzy-search-filter]], [[progress-spinner-waiting]]

## Concept entries these works motivate
The digests surfaced high-value concepts now authored as effects entries (each links back to the case study above):
`procedural-branching` (cbonsai), `decrypt-reveal` (no-more-secrets), `sprite-scroll` (sl, asciiquarium), `color-mask-sprites` (asciiquarium, copilot-cli-banner), `particle-system` (firework-rs), `spectrum-bars` (cava). All live in `../effects/` and resolve.
