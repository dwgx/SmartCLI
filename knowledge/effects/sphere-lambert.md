# Rotating Lambert-shaded sphere (UV parameterization)

A solid sphere rendered by sampling its surface in `(u,v)` spherical
coordinates, rotating each point, projecting with a z-buffer, and picking a
glyph from **Lambert** (diffuse) lighting. The trick that makes it cheap: on a
**unit** sphere the surface point *is* its own normal, so lighting needs no
separate normal computation.

## Formula / params
- Constants (from the shipped effect): `R=1` (radius), `D=4` (viewer distance),
  `K = width·D / (4·R)` (projection scale — fills ~1/2 the width), `ASPECT=0.5`
  (compress vertical so the ball reads round in tall cells).
- Surface sample at `(u,v)`, `u∈[0,2π)` step 0.07, `v∈[0,π)` step 0.04:
  - `x = sin(v)·cos(u)`, `y = sin(v)·sin(u)`, `z = cos(v)` — unit point == normal.
- Rotate `Rx(A)` then `Ry(B)`:
  - `y1 = y·cosA − z·sinA`, `z1 = y·sinA + z·cosA`, `x1 = x`
  - `x2 = x1·cosB + z1·sinB`, `z2 = −x1·sinB + z1·cosB`, `y2 = y1`
- Project (z-buffer holds `inv = 1/zc`, larger = nearer):
  - `zc = z2·R + D`, `inv = 1/zc`
  - `sx = cx + K·x2·R·inv`, `sy = cy − K·y2·R·inv·ASPECT`
  - draw only if `inv > zbuf[sy][sx]`.
- Lambert shading: light `L = (0, 0.707, −0.707)` (front + slightly up);
  `lum = x2·Lx + y2·Ly + z2·Lz` (rotated normal · light), clamp `lum<0 → 0`.
- Glyph: `ramp[int(lum · (len(ramp)−1))]` from the sparse→dense luminance ramp.
- Color (optional): `tint·lum` per channel, or `theme.color_at(lum)`.
- Animation: `A = t·0.9·speed`, `B = t·1.3·speed` (incommensurate rates → the
  ball tumbles rather than spinning about one axis).

## Source
Source: implemented in `skills/cmd-art/fx/effects/sphere.py`; classic
UV-sphere + Lambert diffuse (the same z-buffer/ramp machinery as the donut).

## See also
- [[donut-torus]]
- [[rotation-matrix]]
- [[perspective-projection]]
- [[ascii-luminance-ramp]]
