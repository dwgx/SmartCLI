# termenv — the exact truecolor→256→16 degrade algorithm

Go library whose color code is the drop-in reference for downgrading truecolor to 256 and 16 colors using a *perceptual* distance.

**Source:** https://github.com/muesli/termenv (verified: `color.go`)

## How it works
- **RGB → ANSI 256:** compute two candidates and pick the closer.
  - *Cube candidate:* quantize each channel with `v2ci`: `v < 48 → 0`, `v < 115 → 1`, else `(v-35)/40`. Index `ci = 36*r + 6*g + b`; the value LUT is `[0, 0x5f, 0x87, 0xaf, 0xd7, 0xff]`; result color is `16 + ci`.
  - *Grayscale candidate:* `232 + grayIdx`, where the gray value is `gv = 8 + 10*grayIdx`.
- **ANSI 256 → 16:** brute-force the 16 base colors and keep the nearest.
- **Distance metric:** **HSLuv** (`go-colorful`'s `DistanceHSLuv`), *not* Euclidean RGB — this is what makes the picks look right perceptually.

## What to borrow
- This is the concrete algorithm for SmartCLI's truecolor → 256 → 16 path, including the crucial choice of perceptual (HSLuv) distance over naive RGB distance.
- The cube-vs-gray two-candidate compare avoids the classic "cube can't represent near-grays" artifact.

## See also
- [[nearest-color-downgrade]]
- [[256-color-cube]]
- [[truecolor-24bit]]
- [[color-interpolation]]
