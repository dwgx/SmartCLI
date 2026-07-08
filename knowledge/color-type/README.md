# Terminal Color & Typography — Knowledge Graph

Cross-linked notes on terminal color models, gradients, palettes, image-to-ASCII rendering, and glyph typography. Each entry is one focused concept with an exact formula/escape/config and an authoritative source URL. Grounded in the mined digest (`../sources/raw-color.md`).

## Color models & degrade
- [[truecolor-24bit]] — 24-bit RGB fg/bg escapes and how to detect COLORTERM.
- [[256-color-cube]] — the 6x6x6 cube + grayscale ramp index math.
- [[nearest-color-downgrade]] — tmux's cube-vs-grayscale nearest-match quantizer.

## Gradients & cycling
- [[color-interpolation]] — linear per-channel blend plus sRGB↔linear gamma.
- [[hsv-cycling-lolcat]] — lolcat's three phase-shifted sines for rainbows.

## Palettes
- [[palette-viridis]] — matplotlib's perceptually-uniform default map.
- [[palette-solarized]] — Schoonover's 16-color precision palette.
- [[palette-synthwave84]] — neon retro theme hex set.

## Image → ASCII / ANSI
- [[image-to-ansi-halfblock]] — chafa half-block trick that doubles vertical resolution.

## Typography & glyphs
- [[wcwidth-east-asian-width]] — column-width rules for zero/wide/non-print code points.
- [[figlet-flf-spec]] — FIGfont header fields and smushing rules.
- [[box-drawing]] — U+2500 block glyphs and auto-connecting bitmask logic.
