# Perlin improved noise (2002)

Ken Perlin's improved gradient noise: for each point, find its unit lattice cube, compute smooth fade weights, hash the 8 corner gradients, and trilinearly interpolate their dot products.

## Formula / params (verbatim)
- Fade: `fade(t) = t*t*t*(t*(t*6 - 15) + 10)`.
- Lerp: `lerp(t, a, b) = a + t*(b - a)`.
- Gradient:
  ```
  grad(hash, x, y, z):
    h = hash & 15
    u = h < 8 ? x : y
    v = h < 4 ? y : (h == 12 || h == 14 ? x : z)
    return ((h & 1) == 0 ? u : -u) + ((h & 2) == 0 ? v : -v)
  ```
- `noise()`: floor the coordinate -> unit cube (& 255); compute fade weights u/v/w; hash the 8 corners A/AA/AB/B/BA/BB; trilinearly lerp the corner gradients.
- Permutation table: 256 entries (starts 151, 160, 137, 91, 90, 15, ...), doubled to `p[512]`. Full table is in the raw source file.
- Output range approximately [-1, 1].
- Value noise = same lattice but corners store scalar values instead of gradients.
- Ramp: map `(n + 1)/2` -> ` .:-=+*#%@`.

## Source
Source: https://cs.nyu.edu/~perlin/noise/

## See also
- [[plasma]]
- [[ascii-luminance-ramp]]
