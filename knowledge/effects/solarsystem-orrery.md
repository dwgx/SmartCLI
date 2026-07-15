# Solar-system orrery (tilted 3D orbits in perspective)

Planets ride circular orbits in a plane tilted about the x-axis, so each ring
renders as a perspective **ellipse** (near side larger and brighter, far side
smaller and dimmer). Bodies are depth-sorted (painter's algorithm) so a planet
can pass in front of or behind the sun. Every body completes an **integer**
number of orbits per loop window, so the animation is seamless.

## Formula / params
- Constants (measured from the shipped effect): `ASPECT=2` (a cell is ~2× taller
  than wide), `TILT=0.62` rad (~35° orbital-plane tilt), `FOCAL=2.4` (perspective
  strength), `CAM_Z=3.4` (camera distance), `LOOP_SECONDS=12`.
- Orbit point at radius `r`, angle `a`, tilted about x by `TILT`:
  - `ox = r·cos(a)`
  - `oy = r·sin(a)·cos(TILT)`   (vertical component, compressed by the tilt)
  - `oz = r·sin(a)·sin(TILT)`   (depth component the tilt introduces)
- Perspective projection of a 3D point `(x,y,z)` to screen `(col,row,depth)`:
  - `zc = CAM_Z − z` (clamp to ≥ 0.1); `f = FOCAL / zc`
  - `sx = cx + x·f·scale`
  - `sy = cy − y·f·scale / ASPECT`  (y is up; divide by ASPECT for cell shape)
  - depth key = `zc` (smaller = nearer → wins the z-buffer)
- Scale calibration: sample the outermost ring at `scale=1`, take its projected
  half-extents `hx, hy`, then `scale = min(0.48·w / hx, 0.48·h / hy)` so the
  system fills ~92% of the frame.
- Seamless loop: angular speed `= turns · 2π / LOOP_SECONDS` with `turns` an
  **integer** per body; the sun pulse runs `SUN_PULSE_CYCLES=4` integer cycles.
  State at `t=LOOP` equals `t=0` exactly → capture `LOOP_SECONDS` for a seamless GIF.
- Depth order: collect bodies, paint **far → near** (`sort by −zc`) so nearer
  planets overwrite; each planet gets a fading comet trail sampled at previous
  orbit angles.
- Deterministic star backdrop: a fixed LCG (`s = s·1103515245 + 12345 & 0x7fffffff`)
  seeds `N_STARS` positions, so the field is identical every loop (no flicker).

## Source
Source: implemented in `skills/cmd-art/fx/effects/solarsystem.py`; standard
perspective-projection + painter's-algorithm compositing (see below).

## See also
- [[perspective-projection]]
- [[rotation-matrix]]
- [[terminal-cell-aspect-ratio]]
- [[particle-system]]
