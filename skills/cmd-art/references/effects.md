# cmd-art effects — math & techniques reference

Read this only when adding a new effect or tuning an existing one. All effects
return a full-screen buffer string (height rows joined by `\n`, no trailing
newline, every cell written) and are driven by `run(render, fps, seconds)`.

## ANSI escape reference
- `\x1b[2J` clear screen, `\x1b[H` cursor home (row1/col1), `\x1b[3J` clear scrollback
- `\x1b[?25l` hide cursor, `\x1b[?25h` show cursor
- `\x1b[?1049h` / `\x1b[?1049l` enter / leave alternate screen buffer
- `\x1b[?7l` / `\x1b[?7h` disable / enable line wrap
- `\x1b[38;2;R;G;Bm` truecolor fg, `\x1b[48;2;R;G;Bm` truecolor bg, `\x1b[0m` reset
- Anti-flicker: clear once with `2J`, then each frame emit `\x1b[H` + a full buffer
  where every cell (including blanks) is written. Never `2J` per frame.

## Windows VT enable
`enable_vt()` calls `kernel32.SetConsoleMode(GetStdHandle(-11), mode | 0x1|0x2|0x4)`
(PROCESSED_OUTPUT | WRAP_AT_EOL | VIRTUAL_TERMINAL_PROCESSING). Fallback `os.system("")`.
No-op off Windows.

## Cell aspect
Terminal cells are ~2x taller than wide. Round shapes must compress the vertical
axis by ~0.5 (`ASPECT=0.5`) or sample twice as densely vertically.

## 1. Rotating Lambert-shaded 3D sphere (donut.c method)
1. Unit sphere surface for `u in [0,2pi)`, `v in [0,pi]`:
   `x = sin v cos u`, `y = sin v sin u`, `z = cos v`. For a unit sphere the surface
   normal EQUALS the position vector — free normals.
2. Rotate point and normal together, angles A about X then B about Y:
   - Rx(A): `y' = y cosA - z sinA`, `z' = y sinA + z cosA`, `x'=x`
   - Ry(B): `x'' = x' cosB + z' sinB`, `z'' = -x' sinB + z' cosB`, `y''=y'`
3. Perspective: viewer at origin, sphere at `z=+D` (D~=4 for R=1). `zc = z''R + D`,
   `inv = 1/zc`. `sx = cx + K(x''R)inv`, `sy = cy - K(y''R)inv*ASPECT`.
   `K ~= width*D/(4R)`, `ASPECT~=0.5`. Minus on sy because screen-y grows downward.
4. Z-buffer: store `inv` per cell; larger `inv` = closer = wins.
5. Lambert shade: `lum = N.L`, clamp `<0 -> 0`, ramp index `int(lum*(len(RAMP)-1))`,
   `RAMP=" .:-=+*#%@"` dark->bright. Light `L=(0,0.707,-0.707)`.
   Sampling `du=0.07, dv=0.04` slightly oversamples to avoid pinholes.
   Visible front surface has `z2<0`, so with `lz=-0.707` the lit region lands on the
   surface you actually see. For color, scale a tint by `lum` and keep the z-buffer.

## 2. Big block ASCII text + horizontal truecolor gradient
- Prefer `pyfiglet` (`Figlet(font="standard").renderText(s)`); always keep the stdlib
  fallback `block_text()` using a built-in 5-row `'#'` font (A-Z, 0-9, space).
  Assemble row-by-row with a 1-space gutter. The 5-string-per-glyph format is the
  contract; extend the `FONT` dict for more coverage.
- Gradient: for column `c` of width `W`, `t = c/(W-1)`, lerp each channel
  `chan = a + (b-a)t`. Emit a color escape only when the column color changes
  (run-length), reset at end of each line.
- Animated shimmer: offset `t` by time and feed through HSV hue:
  `t = (c/(W-1) + phase) % 1.0`, `colorsys.hsv_to_rgb(t,1,1)`.

## 3. Plasma / interference wave field
Sum sinusoids of position + one radial term + time; range `[-4,4]`, normalize to `[0,1]`:
```
v(x,y,t) = sin(x*0.10 + t) + sin(y*0.15 + t*0.8)
         + sin((x+y)*0.08 + t*1.2) + sin(hypot(x-cx,y-cy)*0.12 - t)
n = (v + 4) / 8
```
Color: HSV hue = `n` (rainbow), or phase-shifted RGB
`R=128+127 sin(pi n)`, `G=...+2pi/3`, `B=...+4pi/3`. Use BACKGROUND color + space char.
Full-cell repaint means no z-buffer/clear needed. Heaviest effect (O(w*h) escapes);
drop to fps<=20 or shrink dims if it stutters.

## 4. Particle rain (matrix)
Per column: one falling drop with a fractional position `fy` advanced by `speed`
(varied fall rates), `head=int(fy)`. Trail cell `i` behind the head fades by
`1 - i/len`. Head near-white-green, trail pure green. Random printable glyph
(ASCII 33-126) per cell each frame gives the flicker. Respawn above the top once the
whole trail passes the bottom (`head - len > height`).

## Integration notes
- Every `*_frame` returns a full buffer with `height-1` internal newlines and no
  trailing newline; `run()` prepends `\x1b[H` so line 1 col 1 aligns each frame.
- Size from `term_size()` and leave 1 row headroom (auto-size does this); rendering
  into the last row can trigger a scroll. `run()` also disables line wrap.
- Build rows with `"".join(list)`, not `+=`, for the O(w*h) effects.
- Emit color escapes only on change (run-length) to keep buffers small.
- All math verified: unit-sphere normal == position, standard Rx/Ry, one-over-z
  perspective with z-buffer max-wins, ASPECT=0.5, gradient lerp `a+(b-a)t`,
  plasma sum `[-4,4]->[0,1]`, trail fade `1-i/len`.

## See also (knowledge graph)
This is a techniques sampler; the per-effect formulas live sourced in
`D:/Project/SmartCLI/knowledge/` (hubs: `knowledge/effects/README.md`,
`knowledge/color-type/README.md`, index: `knowledge/INDEX.md`):
- Sphere/cube/projection section → [[rotating-cube]] · [[perspective-projection]] · [[rotation-matrix]] · [[ascii-luminance-ramp]] (and [[donut-torus]] for the torus variant)
- Plasma / field section → [[plasma]] · [[tunnel]] · [[perlin-noise]]
- Fire kernel → [[fire-lode]] · [[fire-doom-psx]]
- Matrix rain → [[matrix-rain]] (case studies [[cmatrix]] · [[neo]])
- Block-text / banner → [[figlet-flf-spec]] · [[image-to-ansi-halfblock]]
- Color / gradient / lolcat → [[color-interpolation]] · [[hsv-cycling-lolcat]] · [[truecolor-24bit]]
- Other shipped effects → [[game-of-life]] · [[boids]] · [[starfield]]
