# asciiquarium — animated ASCII aquarium

A terminal aquarium of fish, sharks, and bubbles, built on Perl's `Term::Animation`. The reference for multi-entity ASCII scenes with color and depth.

**Source:** https://github.com/cmatsuoka/asciiquarium (Perl / `Term::Animation`)

## How it works
- Each sprite is ASCII frames **plus a parallel color-mask string** of identical dimensions: each mask cell names a color for the glyph at that position. Glyph layer and color layer are separate but aligned.
- **Depth:** every entity carries an integer depth. Rendering uses a painter's algorithm — draw far-to-near — *not* a pixel z-buffer.
- Callbacks drive per-entity position and frame advance; collisions are scripted (a shark eats a fish → splat).
- A random spawner pool keeps new entities entering the scene.

## What to borrow
- **Color-mask string** for colorizing static art: keep a glyph layer and a same-dimension color layer, so one art asset can be recolored without touching the glyphs.
- **Integer-depth painter's order** — cheaper and simpler than a z-buffer when entities are whole sprites, not sampled surfaces (contrast [[donut-c]]).
- Callback entity + spawner as a lightweight scene-manager pattern.

## See also
- [[sprite-scroll]]
- [[color-mask-sprites]]
- [[ansi-sgr-color]]
- [[cell-grid-model]]
