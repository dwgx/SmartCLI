# ASCII/ANSI Effect Math — Knowledge Graph

Cross-linked notes on the math behind terminal/ASCII visual effects. Each entry is one focused concept with the exact formula, a **Source:** URL, and wiki-style `[[see also]]` links. Grounded in the mined digest (raw findings: `D:/Project/SmartCLI/knowledge/sources/raw-math.md`).

## Effects
- [[donut-torus]] — spinning ASCII torus via `(theta,phi)` sampling, rotation, z-buffer, and `L*8` luminance index.
- [[rotating-cube]] — wireframe cube: rotation matrices + perspective + Bresenham edges.
- [[starfield]] — points fly past on the z-axis, projected and brightened as they near.
- [[tunnel]] — precomputed distance/angle tables sampled from a scrolling texture.
- [[plasma]] — sum of four sines, animated by scrolling the palette only.
- [[fire-lode]] — cooling-buffer fire: average cells below with divisor 129 (~4.0155).
- [[fire-doom-psx]] — DOOM PSX fire: random drift + stochastic decay over a 37-color palette.
- [[game-of-life]] — Conway B3/S23 cellular automaton on 8-cell Moore neighborhoods.
- [[matrix-rain]] — independent falling columns with bright heads and fading tails.
- [[mandelbrot]] — escape-time `z^2+c` from `z0=0`, `c=pixel`, max 1000 iters.
- [[julia-set]] — same iteration with `c` fixed and `z0=pixel`; four classic constants.
- [[perlin-noise]] — improved gradient noise: fade curve, hashed corner grads, trilinear lerp.
- [[boids]] — Reynolds flocking from separation, alignment, and cohesion steering.

## Procedural / entity / particle (composed forms)
- [[procedural-branching]] — stochastic turtle walk with per-type direction dice + cooldown-gated recursion (cbonsai).
- [[decrypt-reveal]] — per-cell countdown + distance-driven glyph churn, lock at zero (no-more-secrets).
- [[sprite-scroll]] — static glyph block blitted at a moving `(x,y)` with a small frame cycle (sl, asciiquarium).
- [[color-mask-sprites]] — glyph layer + parallel color-mask layer; integer-depth painter's order (asciiquarium, copilot banner).
- [[particle-system]] — float pos/vel + gravity + quadratic drag + trail ring buffer + life-ratio brightness (firework-rs).
- [[spectrum-bars]] — log-spaced bins + gravity/integral smoothing + eighth-block sub-cell meter (cava).

## Shared foundations
- [[perspective-projection]] — divide by `z`, scale by focal length.
- [[rotation-matrix]] — basic `Rx`/`Ry`/`Rz` axis rotations.
- [[bresenham-line]] — integer line rasterizer for wireframe edges.
- [[ascii-luminance-ramp]] — map a scalar to a sparse-to-dense glyph string; lists each effect's ramp.
