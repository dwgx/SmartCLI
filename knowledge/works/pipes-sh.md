# pipes.sh — the moving-pipes screensaver

Animated colored pipes that wander the screen, turning at random and drawing proper box-drawing corners at each bend.

**Source:** https://github.com/pipeseroni/pipes.sh (verified: `pipes.sh`, MIT)

## How it works
- A 16-character glyph string encodes every (old direction, new direction) pair. Glyph `= str[old_dir*4 + new_dir]`, with directions `0=up, 1=right, 2=down, 3=left`. E.g. index 12 (right→down) is `┓`.
- **Turning:** turn probability is `(s-1)/s` with `s = 13`. Roll `n = s*RANDOM/32768 - 1`; if `n >= 0` keep direction, else turn `±1` and take `% 4`.
- **Movement:** direction→delta — odd directions move on x, even on y.
- **Draw:** `printf '\e[row;colH'` to position, `tput setaf` for color; edges wrap by modulo; a full-screen reset happens after ~2000 characters drawn.

## What to borrow
- The `(in_dir, out_dir) → 16-glyph` table is the **moving-path specialization** of a 4-edge-weight box-junction table. Same idea as `BoxJunction`, but indexed by motion instead of neighbor connectivity.
- The single-string glyph LUT is a compact, branch-free way to pick corner glyphs.

## See also
- [[box-drawing-glyphs]]
- [[box-drawing]]
- [[cell-grid-model]]
