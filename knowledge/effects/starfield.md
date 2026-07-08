# 3D starfield

Points fly past the viewer along the z-axis; each is perspective-projected, brightened as it nears, and respawned at max depth once it passes the camera.

## Formula / params
- Per frame: `z -= speed`.
- Respawn: if `z <= 0`, reset `x,y = rand`, `z = max_depth`.
- Projection: `sx = (x/z)*scale + cx`, `sy = (y/z)*scale + cy`.
- Brightness: `k = 1 - z/max_depth` (nearer = brighter).
- Ramp: near `@` / `*` -> mid `+` / `.` -> far ` `.

Note: the projection is from the cited source; the motion/respawn/brightness layering is standard demo convention built on top of it.

## Source
Source: https://en.wikipedia.org/wiki/3D_projection

## See also
- [[perspective-projection]]
- [[ascii-luminance-ramp]]
- [[rotating-cube]]
