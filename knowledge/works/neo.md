# neo — truecolor matrix rain

A modern matrix-rain that keeps cmatrix's column model but adds real 24-bit head→tail color interpolation and wide-character (Unicode) glyphs.

**Source:** https://github.com/st3w/neo — color math verified in `src/cloud.cpp` (`Cloud::GetAttr`) + `src/droplet.cpp` (2026-07-08).

## How it works
- Same per-column falling model as [[cmatrix]] (independent columns, bright head, fading tail).
- **Truecolor tail:** each color is a fixed palette of **7 shades** defined in 24-bit via ncurses `init_color(idx,r,g,b)` on the 0–1000 scale (e.g. GREEN pair 1 `(71,141,83)` → pair 7 `(667,1000,941)`). Under `ShadingMode::DISTANCE_FROM_HEAD` the shade is picked by a **discrete linear falloff over palette indices**, not a per-channel RGB lerp: `colorPair = numPairs - round((headLine - line)/length * (numPairs-1))`. Head = brightest shade + bold; tail = shade 1, not bold; middle clamped between. 16-color mode collapses to 2 ANSI pairs. This is per-column [[color-interpolation]] **quantized to 7 steps**.
- Wide characters via `ncursesw`; Unicode is auto-detected from `$LANG` (UTF), color capability from `$TERM`.
- Options: `--glitch` blinks/replaces glyphs, `--async` per-stream timing, `--charset` selects glyph set.

## What to borrow
- Proof that the modern bar is a truecolor palette-interpolated tail (drive it through SmartCLI's `ColorModel`), not flat green.
- Capability autodetection: Unicode from `$LANG`, color depth from `$TERM`, then degrade via [[nearest-color-downgrade]].

## See also
- [[matrix-rain]]
- [[color-interpolation]]
- [[truecolor-24bit]]
- [[nearest-color-downgrade]]
- [[cmatrix]]
