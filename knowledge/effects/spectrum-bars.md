# Spectrum Bars (DSP → sub-cell bar pipeline)

Turn an audio (or any) signal into smooth vertical meter bars: log-spaced frequency bins, EQ normalization, gravity-fall + integral smoothing, autosens, rendered with eighth-block [[sub-cell-resolution]]. From `cava`'s `cavacore.c`. The smoothing half generalizes to **any** animated meter (CPU, progress, levels) — the DSP half is audio-specific.

## Log-spaced bars
```
freq_const   = log10(low/high) / (1/(N+1) − 1)
coeff        = −freq_const + ((n+1)/(N+1)) * freq_const
cut_off_freq[n] = high * pow(10, coeff)          # perceptually even, not linear
```
Per bar: sum `hypot(re, im)` over its FFT bin range (bass bars <100Hz use a 2× bass FFT).

## EQ normalize
`eq[n] = (1/2^28) * pow(cut_off_freq[n+1], 0.85) / log2(FFTsize) / bins_in_band` — tames huge FFT magnitudes and boosts highs.

## Smooth decay (the reusable part)
```
framerate_mod = 66 / framerate
# gravity fall (accelerating), when value dips & noise_reduction > 0.1:
gravity_mod = pow(framerate_mod, 2.5) * 2 / noise_reduction
out = peak * (1 − fall² * gravity_mod)   clamped ≥ 0;   fall += 0.028 each frame
# integral (memory) smoothing:
integral_mod = pow(framerate_mod, 0.1)
out = mem * noise_reduction / integral_mod + out;   mem = out
```

## Autosens
Scale all bars by `sens`: on overshoot (>1.0) `sens *= (1 − 0.02*framerate_mod)`; else `sens *= (1 + 0.001*framerate_mod*autosens)` — so quiet and loud signals both fill the display.

## Render (sub-cell)
Eighth-blocks `U+2581..U+2587` (1/8..7/8) layered over full block `U+2588`: `frac*8` picks the partial-block glyph for smooth vertical resolution.

## Borrow
`frac*8`→eighth-block is [[sub-cell-resolution]] applied vertically to any meter. Gravity+integral falloff is a drop-in "smooth-decay-to-target" filter independent of audio.

**Source:** https://github.com/karlstav/cava (verified `cavacore.c`; distilled in `../sources/deep-art.md` §8)

## See also
- [[cava]]
- [[sub-cell-resolution]]
- [[box-drawing]]
