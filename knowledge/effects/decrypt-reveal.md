# Decrypt / Reveal (Sneakers descramble)

The Hollywood "encrypted text descrambling into readable text" effect: a `CellField` where each cell samples a random glyph from a flux set until its own countdown expires, then locks the target glyph. Cousin of [[matrix-rain]] (shared flux-glyph idea) but per-cell timed rather than per-column scrolled.

## Three phases (no-more-secrets timing)
Constants: `TYPE_EFFECT_SPEED=4ms`, `JUMBLE_SECONDS=2`, `JUMBLE_LOOP_SPEED=35ms`, `REVEAL_LOOP_SPEED=50ms`.
1. **Type-out** — print mask chars, `sleep 4ms` each (wide chars get a 2nd mask char).
2. **Jumble** — `(2000/35) ≈ 57` passes, repaint every cell with a fresh random glyph, `sleep 35ms`.
3. **Reveal** — loop until all cells resolved, `sleep 50ms/pass`.

## Per-cell reveal timer (the core)
```
time = rand() % 5000          # 0..4999 ms, seeded per cell
each reveal pass: time -= 50
  churn (flip to new random mask) with probability:
     rand()%3  == 0   if time < 500     # churns faster near reveal
     rand()%10 == 0   otherwise
  when time <= 0: print the real target glyph and lock
```
Spaces print as-is. Mask/flux glyphs and the ANSI sequences live in separate modules (`nmscharset`, `nmstermio`) — deliberately not reinvented.

## Borrow
Per-cell independent countdown + distance-to-resolve-driven churn probability = a clean text-materialize `CellField`. The "churn faster as the timer nears zero" rule is what sells the descramble. Great for intro/reveal banners.

**Source:** https://github.com/bartobri/no-more-secrets (verified `src/nmseffect.c`; distilled in `../sources/deep-art.md` §6)

## See also
- [[no-more-secrets]]
- [[matrix-rain]]
- [[cell-grid-model]]
- [[ascii-luminance-ramp]]
