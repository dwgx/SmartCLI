# research/ — Archived First-Pass Research

> **Archived provenance material.** These are the raw first-generation research
> notes (2026-07-07), gathered via codex web-search subagents + direct WebFetch.
> They have been **superseded by [`../knowledge/sources/`](../knowledge/sources/)**,
> a fresh 2026-07-08 re-gathering that the live `knowledge/` graph is actually
> built from. The R-docs are kept for provenance and their exact source URLs.
> Formulas and links here remain valid but redundant — for the maintained
> version, follow [`../knowledge/INDEX.md`](../knowledge/INDEX.md).

## Why two source layers

The R1–R7 docs were the initial raw material. When the knowledge graph was
built, the sources were re-fetched into `knowledge/sources/` (`raw-math.md`,
`raw-color.md`, `raw-agent-eng.md`, `deep-art.md`, `deep-tui.md`,
`deep-banner.md`, `works-*.md`). The domain notes under `knowledge/` are mined
from those `sources/` files, **not** from these R-docs. To avoid two sources of
truth, the R-docs were not folded back in — they are frozen here as archive.

## Index — where each doc was folded

| Doc | Topic | Folded into (knowledge domain) |
|---|---|---|
| `R1-effects-catalog.md` | Visual-effect tool landscape + techniques | [`effects/`](../knowledge/effects/README.md), [`works/`](../knowledge/works/README.md) |
| `R2-math-animations.md` | Math / 3D animation formulas | [`effects/`](../knowledge/effects/README.md) |
| `R3-color-typography.md` | Color models, gradients, glyph width | [`color-type/`](../knowledge/color-type/README.md) |
| `R4-tui-patterns.md` | PTY + snapshot interaction patterns | [`tui-patterns/`](../knowledge/tui-patterns/README.md) (still cited) |
| `R5-arch-and-tmux.md` | Plugin architecture + tmux integration | [`agent-eng/`](../knowledge/agent-eng/README.md), [`principles/`](../knowledge/principles/README.md) |
| `R6-tmux-real-behavior.md` | Real tmux behavior for art + driving | [`principles/`](../knowledge/principles/README.md) |
| `R7-terminal-ui-layout.md` | HTML/CSS-like terminal layout + widgets | [`principles/`](../knowledge/principles/README.md), `skills/tui-ui` |
| `_r3_prompt.txt` | Prompt used to generate R3 | — (provenance only) |
| `_fable5_analysis.md` | Unrelated agent-persona evaluation (Chinese) | — (off-topic; not part of the docs graph) |

## Ground-truth assets (kept, actively cited)

These sibling directories are **not** archive — they are measured ground-truth
assets cited by [`../knowledge/ground-truth/`](../knowledge/ground-truth/README.md):

- `cc-decompiled/` — decompiled reference constants
- `real-frames/` — live captures
- `mine-frames/`, `mine-now/` — mined frame assets
