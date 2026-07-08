# Mandelbrot set (escape-time)

For each pixel, iterate `z = z^2 + c` from `z0 = 0` with `c` set to the pixel coordinate; the iteration count before the orbit escapes the radius-2 circle selects the glyph/color.

## Formula / params
- `z0 = 0`, `c = pixel`.
- Iteration (real form): `xtemp = x*x - y*y + x0`; `y = 2*x*y + y0`; `x = xtemp`.
- Continue while `x*x + y*y <= 4` and `iter < max` (max = 1000).
- Viewport: X in (-2.00, 0.47), Y in (-1.12, 1.12).
- Ramp: iteration count -> ` .:-=+*#%@`.

## Source
Source: https://en.wikipedia.org/wiki/Plotting_algorithms_for_the_Mandelbrot_set

## See also
- [[julia-set]]
- [[ascii-luminance-ramp]]
