# firework-rs — particle-system fireworks

Cross-platform ASCII fireworks in the terminal, built on a proper float-position particle simulation with gravity, drag, and glowing trails.

**Source:** https://github.com/Wayoung7/firework-rs (verified: `src/particle.rs`, `src/utils.rs`)

## How it works
- A `Particle { pos, vel, trail: VecDeque, life_state }`. Physics integrates at a fixed sub-step `TIME_STEP = 0.001s`:
  - `vel += dt * (Y*10*grav - vel.normalize() * vel.len()^2 * ar_scale + force)` — gravity plus **quadratic drag** (drag opposes velocity, scales with speed²).
  - `pos += dt * vel`.
- **Life fade:** a life ratio with thresholds `0.4 / 0.65 / 1.0` drives brightness/fade stages.
- **Shapes** by rejection sampling: `gen_points_circle`, `gen_points_circle_normal` (Gaussian, `σ = r/9`), `gen_points_fan(start, end)`, `gen_points_arc`.
- **Color gradients** are scalar curves times a base RGB, e.g. `explosion_gradient_1 = 150x^2` / `|-0.8x + 1.2|`.
- **Trail:** a ring buffer (`VecDeque`) of recent positions; float `pos.round()` maps to a cell (braille sub-cell for smoothness).

## What to borrow
- A reusable **particle kernel**: float pos/vel + gravity + quadratic drag + fixed sub-step + trail ring buffer + life-ratio→brightness gradient. Composite the point samples into a `CellField`, using braille sub-cells for smooth motion.
- Rejection-sampling shape generators are a clean way to author burst patterns.

## See also
- [[particle-system]]
- [[fire-lode]]
- [[color-interpolation]]
- [[sub-cell-resolution]]
- [[rendering-model]]
