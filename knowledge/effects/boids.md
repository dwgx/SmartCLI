# Boids (Reynolds 1987)

Craig Reynolds' flocking model: emergent flock motion from three local steering rules applied to each agent based on its nearby neighbors.

## Formula / params
- Three rules (Reynolds' definitions):
  - Separation: steer to avoid crowding local flockmates.
  - Alignment: steer towards the average heading of local flockmates.
  - Cohesion: steer to move toward the average position of local flockmates.
- Neighbourhood = distance + view-angle from the current heading.
- Update:
  - `cohesion = (avg_pos - pos) * wc`
  - `alignment = (avg_vel - vel) * wa`
  - `separation = sum(pos - other.pos) * ws`
  - `vel += cohesion + alignment + separation`
  - `clamp(vel, max_speed)`
  - `pos += vel`
- Separation typically uses a smaller radius and a larger weight.
- Ramp: direction/velocity glyphs (no luminance ramp; typically arrow/dot characters).

## Source
Source: https://www.red3d.com/cwr/boids/
Source: https://www.red3d.com/cwr/papers/1987/boids.html

## See also
- [[starfield]]
