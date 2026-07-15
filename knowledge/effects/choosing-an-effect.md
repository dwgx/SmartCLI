# Choosing an effect — a decision guide

Not sure how to render something in the terminal? Start here. This note maps
**what you want to show** to a direction, then points at the exact formula note
and the shipped effect you can reuse or take apart. Nothing here is prescriptive
— it's a map. Read the linked note, then either run the ready effect as-is,
tune its params, or compose your own from the primitives it cites.

## The one decision that matters first

- **Recreating something real** (a screenshot, an animation, another program's
  look)? → *measure it first.* Go to [[hard-lessons]] and the worked case
  [[effort-selector]]; capture per-cell truth before writing render code.
- **Designing something new**? → *compose primitives.* Start at
  [[rendering-model]] (the four-primitive kernel), then pull the specific formula
  from the map below.

## "I want to show…" → direction → note → shipped effect

| You want to show… | Direction | Formula note | Reuse (fx effect) |
|---|---|---|---|
| A full-screen moving color field / background | field of sines, animate the palette | [[plasma]] | `plasma` |
| Fire / flames / heat | cooling-buffer cellular fire | [[fire-lode]], [[fire-doom-psx]] | `fire` |
| Falling code / rain / streams | independent columns, bright head + fading tail | [[matrix-rain]] | `rain` |
| A spinning 3D solid (ball, donut) | UV/`(θ,φ)` sampling + rotation + z-buffer + luminance ramp | [[sphere-lambert]], [[donut-torus]] | `sphere`, `donut` |
| A 3D wireframe shape | rotation matrices + perspective + Bresenham edges | [[rotating-cube]], [[perspective-projection]] | `cube` |
| Orbits / planets / a system in motion | tilted orbits, perspective ellipses, painter's depth | [[solarsystem-orrery]] | `solarsystem` |
| Stars / depth / flying through space | points on the z-axis, brighten as they near | [[starfield]], [[tunnel]] | `starfield`, `tunnel` |
| Explosions / sparks / confetti / physics | particles: velocity + gravity + drag + trail + life fade | [[particle-system]] | `fireworks` |
| A living / growing / organic pattern | cellular automaton or stochastic branching | [[game-of-life]], [[procedural-branching]] | `life`, `boids` |
| Big text / a title / a banner | FIGlet glyphs, optionally gradient-colored | [[figlet-flf-spec]], [[ascii-luminance-ramp]] | `text3d`, `banner_scroll`, `gradient_text` |
| A "decrypting / resolving" text reveal | per-cell countdown + glyph churn, lock at zero | [[decrypt-reveal]] | `decrypt` |
| An image as ASCII/ANSI | half-block cells or a luminance ramp | [[image-to-ansi-halfblock]], [[ascii-luminance-ramp]] | `image2ascii` |
| An audio-style bar meter | log-spaced bins + gravity smoothing + eighth-block sub-cell | [[spectrum-bars]] | (compose) |
| A fractal / infinite-zoom math shape | escape-time iteration | [[mandelbrot]], [[julia-set]] | (compose) |
| Smooth organic noise (clouds, terrain) | gradient noise: fade curve + trilinear lerp | [[perlin-noise]] | (compose) |

## When nothing fits exactly

Most "new" effects are a **composition** of a few primitives, not a bespoke
thing. Ask which of these it decomposes into, and pull each from its note:
- **Shape/motion in 3D** → [[perspective-projection]] + [[rotation-matrix]]
  (+ [[terminal-cell-aspect-ratio]] so it isn't squashed).
- **Sub-cell resolution** (smoother curves/bars than one glyph per cell) →
  [[sub-cell-resolution]] (half/quad/braille).
- **Color** → [[color-interpolation]], [[hsv-cycling-lolcat]], and a palette note
  ([[palette-viridis]] / [[palette-synthwave84]] / [[palette-solarized]]).
- **Glyph density from a scalar** → [[ascii-luminance-ramp]].

Then verify the way the [[hard-lessons]] say: run the real script, look at the
real frames, don't head-canon.

## Source
Source: navigation note over `knowledge/effects/` and `knowledge/color-type/`;
the shipped effects live in `skills/cmd-art/fx/effects/`.

## See also
- [[rendering-model]] — the four-primitive kernel for composing anything
- [[hard-lessons]] — measure ground truth before you render
- [[ascii-luminance-ramp]] — the scalar→glyph mapping most effects share
