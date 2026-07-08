# SmartCLI Knowledge Graph — Master Index

One navigable graph over everything SmartCLI knows about building and driving terminal UIs: rendering principles, visual-effect math, color/typography, TUI interaction patterns, agent-engineering for driving CLIs, and measured ground truth. Entries are single-concept notes carrying an exact formula/sequence/constant, a **Source:**, and wiki-style cross-links written as double-bracketed slugs.

## How to use this graph

Pick your lane by task type — this is the core discipline:

- **Replica task** (reproduce a real, existing effect/UI — a screenshot, an animation, another CLI): **measure ground truth first, never head-canon.** Start at [[hard-lessons]] (the ten rules) and the worked case [[effort-selector]]. Decompile / drive-and-capture / screenshot-to-frames → quantify scale + form → extract exact params → build against truth → verify on the real run path.
- **Creative task** (design a new effect/component): **compose primitives.** Start at [[rendering-model]] (the four-primitive kernel), then pull the specific formula from `effects/`, `color-type/`, or `principles/`. Ask "which primitives compose this?" before writing a bespoke widget.

Navigation: each domain has a `README.md` hub; follow the cross-links between entries. A double-bracketed slug names the target filename without `.md`. Cross-domain links are called out with **⇄** below.

## Graph at a glance

| Domain | Hub | What it covers |
|---|---|---|
| Ground truth | [ground-truth/README](ground-truth/README.md) | Measured reality: exact constants, live captures, the replica discipline |
| Principles | [principles/README](principles/README.md) | Terminal rendering foundations: cell grid, SGR, aspect, flicker-free, tmux |
| Effects | [effects/README](effects/README.md) | The math behind ASCII/ANSI visual effects |
| Color & type | [color-type/README](color-type/README.md) | Color models, gradients, palettes, image→ASCII, glyph width |
| TUI patterns | [tui-patterns/README](tui-patterns/README.md) | Driving interactive programs via snapshot observation |
| Agent eng | [agent-eng/README](agent-eng/README.md) | Driving/replicating CLIs with agents; PTY, escape bytes, reverse-engineering |
| Works | [works/README](works/README.md) | Learning from real projects: studied case studies with source URLs + what to borrow |

---

## Ground truth — measure, don't guess
Hub: [ground-truth/README](ground-truth/README.md). The reference standard for replica work.

- [[effort-selector]] — worked violet-ripple selector replica: an 8-row rectangular cosine ripple over aspect-corrected distance, composed as one `field.Ripple` + layout + text-over, plus the SS3 `ESC O C` application-cursor nav gotcha. Implementation: `skills/tui-ui/examples/effort_selector.py`.
- [[hard-lessons]] — ten rules for replicating real effects (ground-truth-first, scale-before-form, multi-frame, real-run verification, CRLF, isatty, UTF-8, self-drive).
- [[rendering-model]] — the four-primitive kernel every widget composes from.

**⇄** [[effort-selector]] draws on [[color-interpolation]] · [[hsv-cycling-lolcat]] · [[terminal-cell-aspect-ratio]] · [[application-cursor-mode]] · [[flicker-free-rendering]].

## Principles — terminal rendering foundations
Hub: [principles/README](principles/README.md). Start here for any creative rendering task.

- Foundations: [[cell-grid-model]] · [[ansi-sgr-color]] · [[cursor-and-screen-control]] · [[flicker-free-rendering]]
- Geometry & measurement: [[terminal-cell-aspect-ratio]] · [[sub-cell-resolution]] · [[cell-width-measurement]]
- Layout on the grid: [[box-model-on-cell-grid]] · [[fractional-space-distribution]] · [[box-drawing-glyphs]]
- tmux behavior: [[truecolor-passthrough-tmux]] · [[tmux-alternate-screen]] · [[resize-sigwinch-handling]] · [[tmux-capture-pane]] · [[tmux-launch-and-sizing]]

**⇄** [[terminal-cell-aspect-ratio]] and [[cell-grid-model]] underpin [[rendering-model]]; [[box-drawing-glyphs]] ⇄ [[box-drawing]] (color-type).

## Effects — the math of visual effects
Hub: [effects/README](effects/README.md). Exact formulas for composed creative effects.

- 3D & projection: [[donut-torus]] · [[rotating-cube]] · [[starfield]] · [[perspective-projection]] · [[rotation-matrix]] · [[bresenham-line]]
- Fields & fractals: [[plasma]] · [[tunnel]] · [[perlin-noise]] · [[mandelbrot]] · [[julia-set]]
- Simulation: [[fire-lode]] · [[fire-doom-psx]] · [[game-of-life]] · [[matrix-rain]] · [[boids]]
- Procedural / entity / particle: [[procedural-branching]] · [[decrypt-reveal]] · [[sprite-scroll]] · [[color-mask-sprites]] · [[particle-system]] · [[spectrum-bars]]
- Shared: [[ascii-luminance-ramp]]

**⇄** [[plasma]] is a `CellField` in [[rendering-model]]; luminance/brightness ties to [[ascii-luminance-ramp]] ⇄ [[image-to-ansi-halfblock]]. The composed forms map back to their case studies: [[procedural-branching]]⇄[[cbonsai]], [[decrypt-reveal]]⇄[[no-more-secrets]], [[sprite-scroll]]⇄[[sl]]/[[asciiquarium]], [[color-mask-sprites]]⇄[[asciiquarium]]/[[copilot-cli-banner]], [[particle-system]]⇄[[firework-rs]], [[spectrum-bars]]⇄[[cava]].

## Color & type — models, gradients, palettes, glyphs
Hub: [color-type/README](color-type/README.md).

- Color models & degrade: [[truecolor-24bit]] · [[256-color-cube]] · [[nearest-color-downgrade]]
- Gradients & cycling: [[color-interpolation]] · [[hsv-cycling-lolcat]]
- Palettes: [[palette-viridis]] · [[palette-solarized]] · [[palette-synthwave84]]
- Image → ASCII: [[image-to-ansi-halfblock]]
- Typography & glyphs: [[wcwidth-east-asian-width]] · [[figlet-flf-spec]] · [[box-drawing]]

**⇄** [[color-interpolation]] builds the [[effort-selector]] palette; [[hsv-cycling-lolcat]] is the `era` rainbow; [[wcwidth-east-asian-width]] ⇄ [[cell-width-measurement]]; [[nearest-color-downgrade]] ⇄ [[truecolor-passthrough-tmux]].

## TUI patterns — driving interactive programs
Hub: [tui-patterns/README](tui-patterns/README.md). Highest-confidence "done" = process-exit / prompt-return; snapshot heuristics layer on top.

- Foundations: [[screen-snapshot-capture]] · [[emulator-libraries]] · [[tmux-capture-pane]] · [[alternate-screen-detection]] · [[application-cursor-mode]] · [[key-encoding-reference]] · [[quiescence-detection]] · [[snapshot-stability-hash]]
- Cross-cutting: [[cursor-row-binding]] · [[verify-movement-step-by-step]] · [[done-signal-layering]]
- Patterns A–H: [[list-menu-navigation]] · [[fuzzy-search-filter]] · [[pager-navigation]] · [[confirm-yes-no-dialog]] · [[progress-spinner-waiting]] · [[form-field-input]] · [[repl-session]] · [[wizard-installer-flow]]

**⇄** [[application-cursor-mode]] ⇄ [[application-cursor-keys-deckm]] (agent-eng) — the exact bug that contaminated [[effort-selector]] navigation; [[verify-movement-step-by-step]] is [[hard-lessons]] applied to input.

## Agent engineering — driving/replicating CLIs with agents
Hub: [agent-eng/README](agent-eng/README.md). The bytes ARE the ground truth.

- Driving via PTY: [[pty-vs-pipe]] · [[pexpect-encoding]] · [[pexpect-no-windows-pty]] · [[node-pty]] · [[node-pty-windows-conpty]] · [[pywinpty]] · [[tmux-send-keys-literal]] · [[tmux-capture-pane]] · [[tmux-control-mode]]
- Escape/TTY gotchas: [[application-cursor-keys-deckm]] · [[alternate-screen-buffer]] · [[bracketed-paste]] · [[crlf-termios]] · [[isatty-branching]]
- Reverse-engineering packed apps: [[strings-utf16le]] · [[ripgrep-binary-search]] · [[node-sea-blob]] · [[source-maps]] · [[hunt-the-esc-byte]]
- Grounding / ACI: [[aci-thesis]] · [[aci-design-rules]] · [[react]] · [[terminal-bench]]

**⇄** The reverse-engineering set (`hunt-the-esc-byte`, `source-maps`) is the general method for recovering a real program's exact bytes/params before replicating it; [[aci-thesis]]/[[terminal-bench]] formalize why [[hard-lessons]] refuses self-report in favor of executed verification.

## Works — learning from real projects
Hub: [works/README](works/README.md). Each entry studies one shipped project — the real technique from its source, what SmartCLI can borrow, and links down into the concepts it demonstrates. Grounded in the deep-dive digests in `sources/` (`deep-art.md`, `deep-tui.md`, `deep-banner.md`); anything not source-confirmed is marked *(verify)*.

- **Visual art:** [[donut-c]] · [[lolcat]] · [[cbonsai]] · [[cmatrix]] · [[neo]] · [[no-more-secrets]] · [[terminaltexteffects]] · [[cava]] · [[pipes-sh]] · [[sl]] · [[asciiquarium]] · [[firework-rs]]
- **TUI frameworks:** [[textual]] · [[ratatui]] · [[bubbletea-lipgloss]] · [[termenv]] · [[notcurses]] · [[chafa]] · [[fzf]] · [[yazi]]
- **Banners & logos:** [[copilot-cli-banner]] · [[gradient-string]] · [[chalk-animation]] · [[cfonts]] · [[figlet]] · [[image-ascii-ramp]] · [[ink-splash-stack]]

Standout case studies: [[terminaltexteffects]] is the motion-architecture reference (`speed → max_steps → eased t → coord`); [[termenv]] is the exact truecolor→256→16 degrade with perceptual HSLuv distance; [[donut-c]] is the canonical z-buffered surface renderer; [[copilot-cli-banner]] shows content-vs-semantic-role color separation.

**⇄** [[donut-c]] demonstrates [[donut-torus]] + [[perspective-projection]] + [[ascii-luminance-ramp]]; [[cmatrix]]/[[neo]] realize [[matrix-rain]]; [[termenv]] is the source algorithm behind [[nearest-color-downgrade]]; [[notcurses]]/[[chafa]] ground [[sub-cell-resolution]] + [[image-to-ansi-halfblock]]; [[textual]]/[[ratatui]] realize [[box-model-on-cell-grid]] + [[fractional-space-distribution]] + [[flicker-free-rendering]]; [[fzf]] is [[fuzzy-search-filter]]. The digests also motivated six composed-form concepts — [[procedural-branching]], [[decrypt-reveal]], [[sprite-scroll]], [[color-mask-sprites]], [[particle-system]], [[spectrum-bars]] — now authored in `effects/` and cross-linked back to their case studies.

---

## Sources / provenance — the raw research tier
Every concept and works entry distills one of these research digests. They are the raw, source-URL-bearing layer under the graph; cite them when promoting a *(verify)* claim.

- **Deep-dives (distilled → entries):** [deep-art](sources/deep-art.md) (visual-art techniques), [deep-tui](sources/deep-tui.md) (TUI frameworks), [deep-banner](sources/deep-banner.md) (banners/logos).
- **Raw surveys (behind the deep-dives):** [works-art](sources/works-art.md), [works-tui](sources/works-tui.md), [works-banner](sources/works-banner.md), [works-galleries](sources/works-galleries.md).
- **Domain source compilations:** [raw-agent-eng](sources/raw-agent-eng.md) (→ agent-eng), [raw-math](sources/raw-math.md) (→ effects), [raw-color](sources/raw-color.md) (→ color-type).

---

## Integrity report

- **Entries:** 92 concept files (across principles, effects, color-type, tui-patterns, agent-eng) + 3 ground-truth entries = **95 concept notes**, plus a **Works wing of 27 case studies** (12 visual art, 8 TUI frameworks, 7 banners/logos) = **122 total**.
- **Sourced:** every concept note carries a **Source:** (URL or explicit *primary/synthesized*). All 27 works entries carry a **real source URL** from the digests — 27/27 sourced; several also cite the exact source file verified (e.g. `lol.rb`, `cbonsai.c`, `motion.py`, `color.go`, `particle.rs`). Digest-flagged uncertainties are marked *(verify)* inline: `neo` (README-level color math), `sl` (constants not re-fetched), `notcurses` `ncpile_rasterize` quantization, `chafa` cost function, and the galleries note.
- **Dangling links:** none. The six formerly-dangling concept slugs — `procedural-branching`, `decrypt-reveal`, `sprite-scroll`, `color-mask-sprites`, `particle-system`, `spectrum-bars` — are now authored in `effects/` and resolve. All wiki-links resolve.
- **Provenance:** all 10 `sources/` digests are reachable — the deep-dives and domain compilations from INDEX + their domain READMEs, the raw surveys from `works/README` and the deep-dives they feed. See the Sources / provenance tier above.
- **Intentional multi-domain slug:** `tmux-capture-pane` exists in three domains (principles / tui-patterns / agent-eng), each a domain-specific angle on the same tool — kept distinct on purpose, now reciprocally cross-linked with `principles/` as the canonical flag reference. The alternate-screen cluster (`tmux-alternate-screen` / `alternate-screen-buffer` / `alternate-screen-detection`) is likewise reciprocally cross-linked.

*Note: cross-domain wiki-links render as plain text in vanilla Markdown viewers; this graph assumes a wiki-link-aware reader (Obsidian-style) resolving a double-bracketed slug to `<domain>/<slug>.md`.*

