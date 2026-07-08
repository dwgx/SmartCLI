# Rotation matrix

Multiply a 3D point by the basic axis rotation matrices `Rx`, `Ry`, `Rz` to spin it before projection.

## Formula / params
- Basic rotation matrices about the x, y, z axes.
- Note: the `Ry` matrix carries `-sin` in the bottom-left entry.
- Used to spin the donut (angles A and B) and the cube.

## Source
Source: https://en.wikipedia.org/wiki/Rotation_matrix

## See also
- [[rotating-cube]]
- [[donut-torus]]
- [[perspective-projection]]
