# Fire (DOOM PSX, Sanglard)

The PlayStation DOOM fire: a fixed hot bottom row spreads upward with a random horizontal drift and a stochastic single-step decay, indexed into a 37-color black->red->orange->yellow->white palette.

## Formula / params
- Buffer: 320x168; bottom row seeded to palette index 36 (hottest).
- `spreadFire(src)`:
  - `randIdx = Math.round(Math.random() * 3.0)`  (0..3)
  - `dst = src - randIdx + 1`
  - `firePixels[dst - FIRE_WIDTH] = pixel - (randIdx & 1)`
  - If the source pixel is 0, the cell above is set to 0.
- Loop `y = 1..H` per column.
- `randIdx` produces wind/horizontal drift; `-(randIdx & 1)` produces stochastic decay (some steps cool, some don't).
- 37-color palette (full RGB triplets black->red->orange->yellow->white) is in the raw source file.
- Ramp: ` .:*oO&8#@`.

## Source
Source: https://fabiensanglard.net/doom_fire_psx/index.html
Source: https://github.com/fabiensanglard/DoomFirePSX/blob/master/flames.html

## See also
- [[fire-lode]]
- [[ascii-luminance-ramp]]
