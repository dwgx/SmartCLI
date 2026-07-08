# Particle System (float pos/vel + drag + trail)

A reusable particle kernel: float `pos`/`vel` integrated with gravity and quadratic drag at a fixed sub-step, each particle carrying a ring-buffer trail and a life-ratio that drives a brightness gradient. Point samples composite into a `CellField`; float positions map to cells via `round()` (or braille [[sub-cell-resolution]] for smoothness). This is `firework-rs`'s core.

## Integration (fixed sub-step)
`TIME_STEP = 0.001s`, looped to fill each frame's duration:
```
vel += dt * ( Y*10*gravity_scale                       # gravity (down)
            − vel.normalize() * vel.length()² * ar_scale  # quadratic air drag (opposes motion)
            + additional_force )
pos += dt * vel
trail.pop_front(); trail.push_back(pos)                 # ring buffer of recent positions
```

## Life fade
`p = elapsed / life_time` → phases `Alive (<0.4) → Declining (<0.65) → Dying (<1.0) → Dead`. The ratio keys brightness/color fade.

## Explosion shapes (rejection sampling → initial velocities)
`gen_points_circle` (x²+y²≤r²), `gen_points_circle_normal` (Gaussian, σ=r/9, dense center), `gen_points_fan(r,n,start,end)` (uniform within an angle range), `gen_points_arc` / `gen_points_on_circle` (`(r·cos a, −r·sin a)`).

## Brightness gradient (scalar 0..1 × base RGB)
```
explosion_gradient_1(x) = 150x²        if x < 0.087   else  −0.8x + 1.2
linear_gradient_1(x)    = −0.7x + 1
```
The scalar drives fade; RGB base comes from config.color. Trail cells draw progressively dimmer.

## Borrow
Float pos/vel + gravity + quadratic drag + fixed sub-step + trail ring buffer + life-ratio→brightness = a general particle layer over `CellField`. Shape generators seed initial velocities. Sub-cell braille smooths motion between whole cells.

**Source:** https://github.com/Wayoung7/firework-rs (verified `src/particle.rs`, `src/utils.rs`; distilled in `../sources/deep-art.md` §12)

## See also
- [[firework-rs]]
- [[fire-lode]]
- [[fire-doom-psx]]
- [[color-interpolation]]
- [[sub-cell-resolution]]
