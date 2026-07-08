# fzf — FuzzyMatchV2 scoring for command palettes

The fuzzy finder whose scoring algorithm is the reference for command-palette and history search. A modified Smith-Waterman DP with tuned bonuses.

**Source:** https://github.com/junegunn/fzf

## How it works
- **FuzzyMatchV2** = a modified Smith-Waterman dynamic-programming match. The core recurrence:
  `H = max(H[i-1][j-1] + 16 + bonus, H[i][j-1] + gap, 0)`.
- **Gap penalties:** gap-start `-3`, gap-extend `-1`.
- **Bonuses:** word boundary `+8`, start-of-string / after-whitespace `+10`, after a delimiter `+9`, camelCase transition `+7`, consecutive match `+4`; the first matched char is doubled (`×2`).
- A parallel C matrix tracks run length for the consecutive bonus. Pipeline: ASCII-gate → compute bonuses → fill an `int16` matrix (score cap `M ≤ 1000`) → backtrace for the match positions.

## What to borrow
- The command-palette / history fuzzy matcher with these exact scoring constants — boundary/BOS/camel bonuses are what make matches feel "smart" instead of naive substring.
- Backtrace positions give you the highlight spans for free.

## See also
- [[fuzzy-search-filter]]
