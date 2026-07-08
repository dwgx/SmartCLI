# lolcat — sine-wave rainbow colorizer

Pipes any text through a diagonal rainbow by cycling RGB with three offset sine waves — the canonical terminal "rainbow text" trick.

**Source:** https://github.com/busyloop/lolcat (verified: `lib/lolcat/lol.rb`)
**Source:** https://github.com/tehmaze/lolcat (Python port; adds the animation loop)

## How it works
- Three sines, offset by `0`, `2π/3`, `4π/3`, give the R/G/B channels: each channel is `sin(freq*i + phase) * 127 + 128`, mapping to 0..255.
- Per character, color is `rainbow(freq, os + i/spread)` where `i` is the column. `os += 1` per line, which shifts the phase and produces the diagonal sweep down the block.
- Emission: truecolor `\e[38;2;r;g;b` when `COLORTERM` advertises it, else nearest 256-color `\e[38;5;n`; reset with `\e[39m`.
- **Animation** (tehmaze port): hide cursor `\e[?25l`, reprint the line, jump back with cursor-left `\e[<len>D`, and advance the phase by `os += spread` each frame — so the rainbow visibly scrolls.

## What to borrow
- This *is* the hue-cycle field: a one-row `CellField` whose color is a function of column + a per-line phase offset. Cheaper than a full HSV→RGB conversion because it's three sines and an affine map.
- The `os += 1/line` phase advance is the minimal recipe for a diagonal gradient.

## See also
- [[hsv-cycling-lolcat]]
- [[truecolor-24bit]]
- [[color-interpolation]]
- [[nearest-color-downgrade]]
