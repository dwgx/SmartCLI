# gradient-string — per-char gradient with column-aligned multiline

The JS library behind most "gradient ASCII art." Its multiline mode is the trick that makes gradients run *vertically* aligned down a text block.

**Source:** https://github.com/bokub/gradient-string (verified: `src/index.ts`)

## How it works
- `colorsCount = max(length_of_string_without_whitespace, stops)`. `tinygradient`'s `.rgb(count)` or `.hsv(count, spin)` yields evenly-spaced samples at `pos = i / (count-1)`.
- **Single-line mode:** loop skips whitespace (no color consumed for spaces) and colors each non-space char with `chalk.hex(colors.shift())`.
- **`multiline()`:** sizes the palette to the **longest line** and consumes a color for *every* character including spaces — so the same column index gets the same color across all lines, and the gradient reads vertically aligned.
- Emission is chalk's `\x1b[38;2;R;G;Bm … \x1b[39m` (truecolor).

## What to borrow
- The **multiline column-alignment trick** — per-char color consumption *including spaces* — is exactly what makes an ASCII-art gradient align vertically instead of skewing per line.
- `interpolation: 'hsv'` + `hsvSpin: 'long'` gives a full rainbow sweep.

## See also
- [[color-interpolation]]
- [[truecolor-24bit]]
- [[hsv-cycling-lolcat]]
