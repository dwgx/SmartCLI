# no-more-secrets — the "decrypt" reveal effect

Recreates the Hollywood/Sneakers "encrypted text descrambling into readable text" effect using pure ANSI/VT100, no dependencies.

**Source:** https://github.com/bartobri/no-more-secrets (verified: `src/nmseffect.c`)

## How it works
Three phases over the captured text:
1. **Type-out** — reprints the source at ~4 ms/char.
2. **Jumble** — ~57 passes at ~35 ms each, each cell showing a random character.
3. **Reveal** — ~50 ms/pass, cells lock to their true glyph over time.

The reveal is per-cell: each character gets a random countdown timer `rand() % 5000`, decremented by `50` per pass. The probability of flipping to a new random mask character is `rand() % 3 == 0` when under 500 ms remain (churns faster near reveal) else `rand() % 10 == 0`. When the timer hits `<= 0`, the cell locks to its target glyph.

## What to borrow
- A clean text-materialize `CellField`: per-cell countdown + distance-driven churn probability, locking to the target when the countdown expires. The "churn faster as you near reveal" rule is what sells it.
- Sub-modules deliberately live elsewhere and were *not* invented here: the mask charset (`nmscharset`) and the escape sequences (`nmstermio`).

## See also
- [[decrypt-reveal]]
- [[matrix-rain]]
- [[ascii-luminance-ramp]]
- [[cell-grid-model]]
