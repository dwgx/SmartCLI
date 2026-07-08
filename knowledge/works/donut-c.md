# donut.c — the spinning ASCII torus

A ~30-line C program that renders a rotating, shaded 3D donut (torus) in ASCII, using nothing but sines, a projection divide, and a z-buffer.

**Source:** https://www.a1k0n.net/2011/07/20/donut-math.html

## How it works
- **Surface:** a circle of radius `R1=1` centered at `R2=2` from the origin, swept through angle `theta` (around the tube) then revolved through `phi` (around the donut). `theta` steps 0.07, `phi` steps 0.02.
- **Spin:** two accumulating angles per frame, `A += 0.04` (x-axis) and `B += 0.02` (z-axis), applied as rotation matrices to every sampled point.
- **Projection:** `ooz = 1/z` (one-over-z); `xp = W/2 + K1*ooz*x`, `yp = H/2 - K1*ooz*y`. The constant `K1 = W*K2*3/(8*(R1+R2))` with `K2=5` bakes screen scale and character aspect into one term.
- **Z-buffer:** stores `ooz` per cell, pre-initialized to 0 (= infinity away). A point is plotted only if its `ooz > buffer[cell]`, so nearer surface wins.
- **Shading:** luminance `L = Ny - Nz` from the surface normal dotted with light direction `(0, 1, -1)`. The ramp `.,-~:;=!*#$@` (12 glyphs) is indexed by `L*8` clamped to 0..11; negative `L` faces away and is skipped.

## What to borrow
- A z-buffered surface renderer as a `CellField`: sample a parametric surface, project with `ooz`, keep nearest by comparing `ooz`.
- The `L*8`-into-ramp idiom is the concrete form of [[ascii-luminance-ramp]].
- Fold aspect + scale into a single `K1` constant so projection is one multiply.

## See also
- [[donut-torus]]
- [[perspective-projection]]
- [[rotation-matrix]]
- [[ascii-luminance-ramp]]
- [[rendering-model]]
- [[terminal-cell-aspect-ratio]]
