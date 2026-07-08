# chafa — 8×8 coverage-bitmap image→Unicode

A C image-to-terminal renderer that matches each cell against a library of Unicode symbols by pixel coverage, for high-fidelity image→ASCII/Unicode.

**Source:** https://github.com/hpjansson/chafa — cost function verified in `chafa/internal/chafa-symbol-renderer.c`, `chafa/chafa-symbol-map.c`, `chafa/internal/chafa-color.h` (2026-07-08).

## How it works
- Each cell is treated as **8×8 pixels (64 sub-pixels)**. The source image is stretched to `w*8 × h*8`.
- Every candidate Unicode symbol has a **coverage bitmap** over that 8×8 grid (which sub-pixels the glyph "fills").
- Per cell: extract a foreground color from the covered pixel group and a background from the uncovered group; score each candidate symbol; pick the best with a stable tie-break.
- Symbol sets include Braille, Sextant, Octant, narrow and wide. Color uses RGB and **DIN99d** perceptual distance, with optional dithering.
- The cost function is **two-stage** (verified in `chafa-symbol-renderer.c` + `chafa-symbol-map.c`, 2026-07-08): (1) a shape prefilter shortlists up to `N_CANDIDATES_MAX = 8` symbols by **Hamming distance = popcount(cell_bitmap XOR symbol_bitmap)** over the 64-bit coverage; (2) among candidates, the winner minimizes the **sum of per-pixel squared color distance** `Σ chafa_color_diff_fast(pair[cov_i], pixel_i)` (`calc_cell_error_plain`), where `chafa_color_diff_fast` = squared Euclidean `Δ²` computed in RGB or, for DIN99d mode, in the DIN99d-transformed space (`L·2.5`, `C·cos h·2.5+128`, `C·sin h·2.5+128`). So popcount picks the shape; squared color error picks the final symbol.

## What to borrow
- The **8×8 coverage-bitmap symbol-match** model for image→Unicode: far higher fidelity than a fixed luminance ramp because it matches *shape*, not just brightness.
- Splitting each cell into a covered/uncovered pixel group to derive the two cell colors — the same "2 colors per cell" reality as [[notcurses]].

## See also
- [[image-to-ansi-halfblock]]
- [[sub-cell-resolution]]
- [[nearest-color-downgrade]]
