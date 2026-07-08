# ASCII luminance ramp

Map a computed scalar (brightness, height, iteration count, noise value) to a character from a ramp ordered from "empty/dark" to "dense/bright", so denser glyphs read as brighter.

## Formula / params
- General convention: pick an index into an ordered glyph string from the effect's scalar, e.g. donut uses `index = L*8` into `".,-~:;=!*#$@"`.
- Per-effect ramps (each sourced in its own file):
  - Donut: `".,-~:;=!*#$@"` (12 chars) — see [[donut-torus]].
  - Tunnel: ` .:-=+*#` — see [[tunnel]].
  - Plasma / Mandelbrot / Julia / Perlin: ` .:-=+*#%@` — see [[plasma]], [[mandelbrot]], [[julia-set]], [[perlin-noise]].
  - Fire (both): ` .:*oO&8#@` — see [[fire-lode]], [[fire-doom-psx]].
  - Matrix (mono): `@`/`#` -> `+`/`=` -> `:`/`.` -> ` ` — see [[matrix-rain]].
  - Life: live `#`/`O`, dead ` `/`.` — see [[game-of-life]].
  - Starfield: near `@`/`*` -> mid `+`/`.` -> far ` ` — see [[starfield]].
- The general "order glyphs from sparse to dense" principle is a shared, well-established convention (primary/synthesized); the individual ramps above are drawn from each effect's cited source.

## Source
Source: https://www.a1k0n.net/2011/07/20/donut-math.html (donut ramp and `L*8` index; the general sparse→dense ramp convention is primary/synthesized, and each specific ramp cites its own effect's source)

## See also
- [[donut-torus]]
- [[tunnel]]
- [[plasma]]
- [[fire-lode]]
- [[mandelbrot]]
- [[perlin-noise]]
