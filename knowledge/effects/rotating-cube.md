# Rotating cube / wireframe

A 3D cube (or any wireframe) spun with rotation matrices, projected to 2D, and drawn edge-by-edge with a line-rasterization algorithm.

## Formula / params
- Rotate vertices with basic rotation matrices `Rx`, `Ry`, `Rz` (note: the `Ry` matrix carries `-sin` in the bottom-left entry).
- Perspective projection: `sx = (x/z)*focal + cx`, `sy = (y/z)*focal + cy`.
- Draw the 12 cube edges as lines via Bresenham's line algorithm.
- Ramp: edge glyphs `#` / `*` / `.`.

## Source
Source: https://en.wikipedia.org/wiki/Rotation_matrix
Source: https://en.wikipedia.org/wiki/3D_projection
Source: https://en.wikipedia.org/wiki/Bresenham%27s_line_algorithm

## See also
- [[rotation-matrix]]
- [[perspective-projection]]
- [[bresenham-line]]
- [[donut-torus]]
