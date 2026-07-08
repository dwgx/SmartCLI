# cava — console audio spectrum visualizer

Real-time audio spectrum bars in the terminal, with log-spaced frequency bins, EQ, and gravity-based smooth decay.

**Source:** https://github.com/karlstav/cava (verified: `cavacore.c`)

## How it works
- **Log-spaced bars:** cutoff per bar `cut_off_freq[n] = high * pow(10, coeff)` so bins are perceptually even, not linear.
- **EQ:** `(1/2^28) * pow(f, 0.85) / log2(FFTsize) / bins` weights each bin.
- **Gravity fall:** a peak decays with `out = peak * (1 - fall^2 * gravity_mod)`, `fall += 0.028` — accelerating fall like gravity.
- **Integral smoothing:** memory term `out = mem * nr / integral_mod + out` smooths jitter across frames.
- **Autosens:** scales output by a `sens` factor — shrink 2% on overshoot, grow 0.1% otherwise — so quiet and loud signals both fill the display.
- **Render:** eighth-blocks `U+2581..U+2587` layered over full block `U+2588` give sub-cell *vertical* resolution: `frac * 8` picks the partial-block glyph.

## What to borrow
- Eighth-block sub-cell bars (`frac*8` → glyph) are the concrete [[sub-cell-resolution]] technique for any vertical meter.
- Gravity fall + integral memory is a reusable **smooth-decay-to-target** filter for *any* meter (CPU, progress, levels), not just audio.

## See also
- [[spectrum-bars]]
- [[sub-cell-resolution]]
- [[box-drawing]]
- [[box-drawing-glyphs]]
