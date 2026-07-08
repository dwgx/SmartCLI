# Julia set

The same `z^2 + c` escape-time iteration as Mandelbrot, but `c` is a fixed constant and `z0` is the pixel coordinate, producing a distinct fractal per chosen constant.

## Formula / params
- `z0 = pixel`, `c = fixed constant`.
- Same iteration and escape test: continue while `x^2 + y^2 > 4` is not yet true (escape at `x^2 + y^2 > 4`).
- Common constants: `c = -0.7 + 0.27015i`, `-0.8 + 0.156i`, `0.285 + 0.01i`, `-0.4 + 0.6i`.
- Ramp: iteration count -> ` .:-=+*#%@`.

## Source
Source: https://en.wikipedia.org/wiki/Plotting_algorithms_for_the_Mandelbrot_set

## See also
- [[mandelbrot]]
- [[ascii-luminance-ramp]]
