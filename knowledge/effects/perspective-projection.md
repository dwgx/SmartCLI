# Perspective projection

Divide 3D coordinates by depth `z` and scale by a focal length to map them onto the 2D screen; closer objects appear larger.

## Formula / params
- `sx = (x/z)*focal + cx`, `sy = (y/z)*focal + cy` (cx, cy = screen center).
- In the donut, projection uses `1/z` directly with scale `K1` and a `1/z` z-buffer.

## Source
Source: https://en.wikipedia.org/wiki/3D_projection

## See also
- [[donut-torus]]
- [[rotating-cube]]
- [[starfield]]
- [[rotation-matrix]]
