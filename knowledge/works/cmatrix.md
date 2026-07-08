# cmatrix — the reference matrix-rain implementation

The classic terminal "digital rain": green glyphs streaming down columns with a bright white head and a fading green tail.

**Source:** https://github.com/abishekvashok/cmatrix (verified: `cmatrix.c`, GPLv3)

## How it works
- Per-column state `{val, is_head}` plus parallel arrays for `length`, `spaces`, and `updates`. Only **even columns** are used (readable spacing).
- Init per column: gap `= rand % LINES + 1`, run length `= rand % (LINES - 3) + 3`, speed `= rand % 3 + 1`.
- A global `count` (1..4) gates asynchronous advance so columns fall at staggered rates.
- The **head** is seeded at row 0 and detaches (moves down) once `y > length`. Head is drawn white/bold; the tail is green.
- Charset: default ASCII `33..123`; katakana build uses `0xff66..0xff9d` (half-width kana).
- Timing: `napms(update*10)` ≈ 40 ms per tick.

## What to borrow
- A per-column 1D "shader": `{head, len, gap, speed}` per column is the minimal state for rain. The head/tail brightness split is just a column-local [[ascii-luminance-ramp]].
- Even-columns-only and randomized gap/len/speed are the cheap tricks that make it read as rain rather than noise.

## See also
- [[matrix-rain]]
- [[ascii-luminance-ramp]]
- [[cell-grid-model]]
